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
        env = patch.dict(os.environ, {"QIUZHAO_PLATFORM_MODEL_DAILY_LIMIT": "100"})
        env.start()
        self.addCleanup(env.stop)
        self.anon = TestClient(server.app)

    def invited(self, label="测试用户", quota=30):
        session = self.store.redeem(self.store.invite(label), quota)
        client = TestClient(server.app, headers={"Authorization": "Bearer " + session})
        return session, client

    def test_cors_only_exact_https_preview_origin(self):
        self.assertEqual(["https://preview.example.invalid"],
                         server.trusted_origins("https://preview.example.invalid"))
        self.assertEqual([], server.trusted_origins(""))
        for bad in ("*", "http://public.example.invalid", "https://preview.example.invalid/path",
                    "https://user:password@preview.example.invalid"):
            with self.assertRaises(ValueError):
                server.trusted_origins(bad)

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
        self.assertEqual(2, self.store.quota(self.store.user(session), 100)["model_calls_used"])

    def test_platform_cap_cross_user_and_retries_do_not_escape(self):
        first_token, first = self.invited("甲")
        second_token, second = self.invited("乙")
        with patch.dict(os.environ, {"QIUZHAO_PLATFORM_MODEL_DAILY_LIMIT": "2"}):
            self.store.consume(self.store.user(first_token), "model", platform_daily_limit=2)
            self.store.consume(self.store.user(second_token), "model", platform_daily_limit=2)
            self.assertEqual(0, first.get("/api/quota").json()["model_calls_remaining"])
            self.assertTrue(second.get("/api/quota").json()["platform_limit_reached"])
            env = {"QIUZHAO_LLM_API_KEY": "dummy", "QIUZHAO_LLM_BASE_URL": "https://example.invalid/v1",
                   "QIUZHAO_LLM_MODEL": "fake", "QIUZHAO_PLATFORM_MODEL_DAILY_LIMIT": "2"}
            with patch.dict(os.environ, env), patch.object(server.resume_gen, "llm_chain",
                 side_effect=lambda *_: llm.chat("dummy", retries=2)), \
                 patch.object(llm.urllib.request, "urlopen") as outbound:
                result = second.post("/api/resume", json=PAYLOAD)
            self.assertEqual(429, result.status_code)
            self.assertIn("平台", result.json()["detail"])
            outbound.assert_not_called()

    def test_atomic_platform_limit_under_parallel_users(self):
        first, second = (self.store.user(self.invited(label)[0]) for label in ("甲", "乙"))
        def consume(user):
            try:
                self.store.consume(user, "model", platform_daily_limit=1)
                return True
            except access.AccessError as exc:
                self.assertEqual(429, exc.status)
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual([False, True], sorted(pool.map(consume, (first, second))))
        with closing(self.store.connect()) as db:
            self.assertEqual(1, db.execute("SELECT COUNT(*) FROM usage WHERE kind = 'model'").fetchone()[0])

    def test_state_store_inside_repository_and_http_model_url_rejected(self):
        project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with self.assertRaises(ValueError):
            access.AccessStore(os.path.join(project, "agent", "state", "access.sqlite3"))
        env = {"QIUZHAO_LLM_API_KEY": "dummy", "QIUZHAO_LLM_BASE_URL": "http://model.example.invalid/v1",
               "QIUZHAO_LLM_MODEL": "fake"}
        with patch.dict(os.environ, env), patch.object(llm.urllib.request, "urlopen") as outbound:
            with self.assertRaises(llm.LLMError):
                llm.chat("synthetic")
            outbound.assert_not_called()

    def test_platform_limit_missing_or_invalid_fails_closed(self):
        token, client = self.invited()
        with self.assertRaises(ValueError):
            self.store.consume(self.store.user(token), "model")
        with patch.dict(os.environ, {"QIUZHAO_PLATFORM_MODEL_DAILY_LIMIT": "0"}):
            with patch.object(server.llm, "is_configured", return_value=True), \
                 patch.object(server.resume_gen, "llm_chain") as chain:
                self.assertEqual(503, client.post("/api/resume", json=PAYLOAD).status_code)
                chain.assert_not_called()
            self.assertEqual(503, client.get("/api/quota").status_code)

    def test_platform_quota_resets_at_beijing_midnight(self):
        # 当前时间附近跨越北京时间午夜，不依赖具体生产日期。
        token, _ = self.invited()
        from datetime import datetime, timedelta
        midnight = datetime.combine(datetime.now(access.CN_TZ).date() + timedelta(days=1),
                                    datetime.min.time(), tzinfo=access.CN_TZ)
        cutoff = midnight.timestamp()
        user_id = self.store.user(token)
        with patch.object(access.time, "time", side_effect=[cutoff - 1, cutoff]):
            self.store.consume(user_id, "model", platform_daily_limit=1)
            self.store.consume(user_id, "model", platform_daily_limit=1)
        with closing(self.store.connect()) as db:
            days = db.execute("SELECT DISTINCT day FROM usage WHERE kind = 'model' ORDER BY day").fetchall()
            self.assertEqual(2, len(days))

    def test_per_user_quota_override_and_zero_limit(self):
        token, client = self.invited(quota=1)
        user = self.store.user(token)
        self.store.consume(user, "model", platform_daily_limit=100)
        with self.assertRaises(access.AccessError) as caught:
            self.store.consume(user, "model", platform_daily_limit=100)
        self.assertEqual(429, caught.exception.status)
        self.store.set_quota(user, 3)
        self.store.consume(user, "model", platform_daily_limit=100)
        self.assertEqual(1, client.get("/api/quota").json()["model_calls_remaining"])
        self.store.set_quota(user, 0)
        with self.assertRaises(access.AccessError):
            self.store.consume(user, "model", platform_daily_limit=100)


if __name__ == "__main__":
    unittest.main()
