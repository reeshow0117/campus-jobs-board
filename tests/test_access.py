"""邀请、撤销、并发兑换、用户级限流和实际模型 HTTP 尝试的离线回归。"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from fastapi.testclient import TestClient
from agent import access, llm, server
from test_resume_flow import MATERIALS, PROFILE, MARKDOWN

PAYLOAD = {"source": "browser", "profile": PROFILE, "materials": MATERIALS, "title": "产品经理"}


class AccessTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "access.sqlite3")
        self.store = access.AccessStore(self.path)
        self.store.init()
        self.assertEqual(0o600, os.stat(self.path).st_mode & 0o777)
        for name, value in (("ACCESS_DB", self.path), ("PRIVATE_VAULT", False)):
            p = patch.object(server, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.anon = TestClient(server.app)

    def invited(self, label="测试用户", quota=30):
        session = self.store.redeem(self.store.invite(label), quota)
        client = TestClient(server.app, headers={"Authorization": "Bearer " + session})
        return session, client

    def test_anonymous_denied_and_fail_closed_without_db(self):
        self.assertEqual(401, self.anon.post("/api/resume", json=PAYLOAD).status_code)
        self.assertEqual(401, self.anon.post("/api/resume_pdf", json={
            **PAYLOAD, "markdown": MARKDOWN}).status_code)
        self.assertEqual(401, self.anon.get("/api/quota").status_code)
        with patch.object(server, "ACCESS_DB", ""):
            self.assertEqual(503, self.anon.post("/api/resume", json=PAYLOAD).status_code)
            self.assertEqual(503, self.anon.post("/api/invite/redeem", json={"invite_code": "x" * 40}).status_code)

    def test_one_time_invite_and_session_revocation(self):
        code = self.store.invite("受邀用户")
        redeemed = self.anon.post("/api/invite/redeem", json={"invite_code": code})
        self.assertEqual(200, redeemed.status_code)
        token = redeemed.json()["access_token"]
        self.assertEqual(403, self.anon.post("/api/invite/redeem", json={"invite_code": code}).status_code)
        with open(self.path, "rb") as file:
            self.assertNotIn(code, file.read().decode("utf-8", errors="ignore"))
        client = TestClient(server.app, headers={"Authorization": "Bearer " + token})
        self.assertEqual(30, client.get("/api/quota").json()["model_calls_remaining"])
        self.store.revoke(self.store.user(token))
        self.assertEqual(401, client.get("/api/quota").status_code)

    def test_concurrent_redemption_only_one_wins(self):
        code = self.store.invite("同一个邀请")
        def attempt(_):
            try:
                self.store.redeem(code, 3)
                return True
            except access.AccessError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual([False, True], sorted(pool.map(attempt, range(2))))

    def test_expired_invite_and_session_rejected(self):
        code = self.store.invite("过期")
        with closing(self.store.connect()) as db, db:
            db.execute("UPDATE invites SET expires_at = 1")
        self.assertEqual(403, self.anon.post("/api/invite/redeem", json={"invite_code": code}).status_code)
        session, client = self.invited()
        with closing(self.store.connect()) as db, db:
            db.execute("UPDATE sessions SET expires_at = 1 WHERE token_hash = ?", (access.digest(session),))
        self.assertEqual(401, client.get("/api/quota").status_code)

    def test_rate_limit_is_per_user_and_shared_by_pdf(self):
        _, client = self.invited("甲")
        _, other = self.invited("乙")
        with patch.object(server.llm, "is_configured", return_value=True), \
             patch.object(server.resume_gen, "llm_chain", return_value=MARKDOWN):
            for _ in range(6):
                self.assertEqual(200, client.post("/api/resume", json=PAYLOAD).status_code)
            limited = client.post("/api/resume_pdf", json={**PAYLOAD, "markdown": MARKDOWN})
            self.assertEqual(429, limited.status_code)
            self.assertIn("Retry-After", limited.headers)
            self.assertEqual(200, other.post("/api/resume", json=PAYLOAD).status_code)

    def test_model_attempts_include_retries_and_reject_before_outbound(self):
        session, client = self.invited(quota=2)
        env = {"QIUZHAO_LLM_API_KEY": "dummy", "QIUZHAO_LLM_BASE_URL": "https://example.invalid/v1",
               "QIUZHAO_LLM_MODEL": "fake"}
        def generate(*_):
            return llm.chat("dummy", retries=2)
        with patch.dict(os.environ, env), patch.object(server.resume_gen, "llm_chain", side_effect=generate), \
             patch.object(llm.urllib.request, "urlopen", side_effect=urllib.error.URLError("offline")) as outbound, \
             patch.object(llm.time, "sleep"):
            result = client.post("/api/resume", json=PAYLOAD)
        self.assertEqual(429, result.status_code)
        self.assertEqual(2, outbound.call_count)
        self.assertEqual(0, client.get("/api/quota").json()["model_calls_remaining"])
        self.assertEqual(2, self.store.quota(self.store.user(session))["model_calls_used"])

    def test_per_user_quota_override_and_zero_limit(self):
        token, client = self.invited(quota=1)
        user = self.store.user(token)
        self.store.consume(user, "model")
        with self.assertRaises(access.AccessError) as caught:
            self.store.consume(user, "model")
        self.assertEqual(429, caught.exception.status)
        self.store.set_quota(user, 3)
        self.store.consume(user, "model")
        self.assertEqual(1, client.get("/api/quota").json()["model_calls_remaining"])
        self.store.set_quota(user, 0)
        with self.assertRaises(access.AccessError):
            self.store.consume(user, "model")


if __name__ == "__main__":
    unittest.main()
