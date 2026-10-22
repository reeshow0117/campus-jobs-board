"""仅用于真实浏览器回归的本机测试服务，使用模拟模型和虚构资料。"""
from pathlib import Path
import json
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_model_integration import model_server
from test_resume_flow import MARKDOWN, PROFILE, MATERIALS, fake_photo
from agent import access, server
import uvicorn


if __name__ == "__main__":
    replies = [json.dumps({"role": "产品经理", "must_have": ["需求分析"]}),
               json.dumps([{"id": "E1"}, {"id": "S1"}]), MARKDOWN]
    with tempfile.TemporaryDirectory() as state, model_server(replies):
        server.ACCESS_DB = os.path.join(state, "access.sqlite3")
        server.PRIVATE_VAULT = False
        os.environ["QIUZHAO_PLATFORM_MODEL_DAILY_LIMIT"] = "12"
        store = access.AccessStore(server.ACCESS_DB)
        store.init()
        code = store.invite("browser-test")

        @server.app.get("/__test_fixture")
        def fixture():
            return {"invite": code, "profile": PROFILE, "materials": MATERIALS, "photo": fake_photo()}

        uvicorn.run(server.app, host="127.0.0.1", port=8765, log_level="warning")
