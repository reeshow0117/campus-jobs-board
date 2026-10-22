"""真实回环 HTTP 模型服务，覆盖三次调用、用量和最终 PDF，不使用真 Key。"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
import threading
import time
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from agent import llm, public_config
import test_resume_flow as fixtures
from test_resume_flow import MARKDOWN, fake_photo


@contextmanager
def model_server(responses):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            content = responses[min(len(calls) - 1, len(responses) - 1)]
            self.wfile.write(json.dumps({"choices": [{"message": {"content": content},
                                                    "finish_reason": "stop"}]}).encode())

        def log_message(self, *_):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        with patch.dict(os.environ, {
            "QIUZHAO_LLM_API_KEY": "synthetic-only", "QIUZHAO_LLM_MODEL": "test",
            "QIUZHAO_LLM_BASE_URL": f"http://127.0.0.1:{httpd.server_port}",
        }):
            yield calls
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


class ModelIntegrationTests(unittest.TestCase):
    setUp = fixtures.ResumeFlowTests.setUp

    def test_http_chain_to_pdf_and_exact_usage(self):
        replies = [json.dumps({"role": "产品经理", "must_have": ["需求分析"]}),
                   json.dumps([{"id": "E1"}, {"id": "S1"}]), MARKDOWN]
        with model_server(replies) as calls:
            result = self.client.post("/api/resume", json={**self.payload, "title": "产品经理"})
        self.assertEqual(200, result.status_code, result.text)
        self.assertEqual([], result.json()["warnings"])
        self.assertEqual(3, len(calls))
        self.assertEqual(3, self.client.get("/api/quota").json()["model_calls_used"])
        pdf = self.client.post("/api/resume_pdf", json={**self.payload,
            "markdown": result.json()["markdown"], "photo_data_url": fake_photo()})
        self.assertEqual(200, pdf.status_code)
        self.assertEqual(1, len(PdfReader(io.BytesIO(pdf.content)).pages))


class ModelFailureTests(unittest.TestCase):
    def test_provider_auth_failure_is_not_retried_or_leaked(self):
        import urllib.error
        env = {"QIUZHAO_LLM_API_KEY": "secret-test-key", "QIUZHAO_LLM_BASE_URL": "https://api.deepseek.com",
               "QIUZHAO_LLM_MODEL": "deepseek-flash"}
        error = urllib.error.HTTPError(env["QIUZHAO_LLM_BASE_URL"], 401, "unauthorized", {},
                                      io.BytesIO(b"secret-test-key upstream private response"))
        with patch.dict(os.environ, env), patch.object(llm, "open_model", side_effect=error) as outbound:
            with self.assertRaises(llm.LLMError) as caught:
                llm.chat("synthetic")
        self.assertEqual(1, outbound.call_count)
        self.assertIn("密钥无效", caught.exception.public_message)
        self.assertNotIn("secret-test-key", str(caught.exception))
        self.assertEqual({"type": "disabled"}, json.loads(outbound.call_args.args[0].data)["thinking"])

    def test_empty_or_malformed_content_is_controlled(self):
        for content in (None, "", {"unexpected": "shape"}):
            with self.subTest(content=content), model_server([content]):
                with self.assertRaises(llm.LLMError):
                    llm.chat("synthetic", retries=0)

    def test_expired_deadline_does_not_charge_or_send(self):
        token = llm.deadline.set(time.monotonic() - 1)
        from unittest.mock import Mock
        charge = Mock()
        meter = llm.charge_attempt.set(charge)
        try:
            with model_server(["never used"]) as calls:
                with self.assertRaises(llm.LLMError):
                    llm.chat("synthetic")
                self.assertEqual([], calls)
                charge.assert_not_called()
        finally:
            llm.deadline.reset(token)
            llm.charge_attempt.reset(meter)

    def test_public_config_never_exposes_private_environment(self):
        with patch.dict(os.environ, {"QIUZHAO_LLM_API_KEY": "DO-NOT-PUBLISH",
                                    "QIUZHAO_PUBLIC_API_URL": "https://api.example.invalid"}):
            config = public_config.javascript()
        self.assertNotIn("DO-NOT-PUBLISH", config)
        self.assertIn("https://api.example.invalid", config)
