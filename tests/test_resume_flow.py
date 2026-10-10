"""平台简历主链路回归：不用真 LLM、也不读取任何私人资料。"""
import base64
import io
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader

from agent import access, resume_gen, resume_pdf, server

PROFILE = {"name": "测试候选人", "edu": "本科", "contact": "", "expect_job": "产品经理"}
MATERIALS = [
    {"id": "E1", "org": "样例大学", "role": "软件工程", "period": "2023-2027", "body": "- 学习软件开发"},
    {"id": "S1", "org": "样例公司", "role": "产品实习生", "period": "2026", "body": "- 完成需求分析"},
]
MARKDOWN = """# 测试候选人 - 产品经理

## 教育经历
### E1 | 样例大学 | 软件工程 | 2023-2027
- **教育：**学习软件开发 [@E1]

## 实习经历
### S1 | 样例公司 | 产品实习生 | 2026
- **项目：**完成需求分析 [@S1]
"""


def fake_photo():
    image = Image.new("RGB", (160, 220), (232, 235, 239))
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


class ResumeFlowTests(unittest.TestCase):
    def setUp(self):
        state_dir = tempfile.TemporaryDirectory()
        self.addCleanup(state_dir.cleanup)
        path = os.path.join(state_dir.name, "access.sqlite3")
        store = access.AccessStore(path)
        store.init()
        session = store.redeem(store.invite("测试受邀者"), 30)
        db_patch = patch.object(server, "ACCESS_DB", path)
        db_patch.start()
        self.addCleanup(db_patch.stop)
        self.client = TestClient(server.app, headers={"Authorization": "Bearer " + session})
        self.profile = PROFILE.copy()
        self.materials = [m.copy() for m in MATERIALS]
        self.payload = {"source": "browser", "profile": self.profile, "materials": self.materials}
        self.vault_patch = patch.object(server, "PRIVATE_VAULT", False)
        self.vault_patch.start()
        self.addCleanup(self.vault_patch.stop)

    def test_public_mode_never_reads_local_vault(self):
        with patch.object(server.vault_loader, "load_vault", side_effect=AssertionError("私库被访问")):
            self.assertFalse(self.client.get("/api/capabilities").json()["private_vault"])
            self.assertEqual(403, self.client.post("/api/reload").status_code)
            self.assertEqual(403, self.client.post("/api/resume", json={"source": "local_vault", "title": "产品"}).status_code)
            with patch.object(server.llm, "is_configured", return_value=True):
                with patch.object(server.resume_gen, "llm_chain", return_value=MARKDOWN):
                    result = self.client.post("/api/resume", json={**self.payload, "title": "产品"})
            self.assertEqual(200, result.status_code)
            self.assertEqual([], result.json()["warnings"])

    def test_single_page_pdf_photo_and_safe_spacing(self):
        result = self.client.post("/api/resume_pdf", json={
            **self.payload, "markdown": MARKDOWN, "photo_data_url": fake_photo()})
        self.assertEqual(200, result.status_code, result.text[:200] if result.status_code != 200 else "")
        self.assertEqual(1, len(PdfReader(io.BytesIO(result.content)).pages))
        # PyMuPDF 用于检查照片与水平分隔线没有重叠；CI 已声明 test extra。
        import pymupdf
        page = pymupdf.open(stream=result.content, filetype="pdf")[0]
        photos = [rect for image in page.get_images(full=True)
                  for rect in page.get_image_rects(image[0])]
        rules = [drawing["rect"] for drawing in page.get_drawings() if drawing["rect"].height < 2]
        self.assertTrue(photos)
        self.assertFalse(any(photo.intersects(rule) for photo in photos for rule in rules))

    def test_no_photo_or_invalid_source_is_rejected(self):
        req = {**self.payload, "markdown": MARKDOWN}
        self.assertEqual(400, self.client.post("/api/resume_pdf", json=req).status_code)
        self.assertEqual(400, self.client.post("/api/resume_pdf", json={**req, "photo_data_url": "data:image/png;base64,Zm9v"}).status_code)
        self.assertEqual(422, self.client.post("/api/resume_pdf", json={
            **req, "markdown": MARKDOWN.replace("[@S1]", "[@S999]"),
            "photo_data_url": fake_photo()}).status_code)

    def test_markup_escaping_and_overflow(self):
        self.assertIn("&lt;script&gt;", resume_pdf.md_inline("<script>**重点**"))
        self.assertIn("<b>重点</b>", resume_pdf.md_inline("<script>**重点**"))
        self.assertTrue(resume_gen.verify_resume(MARKDOWN.replace("[@E1]", "[@E900]"),
                        {m["id"]: m for m in self.materials}))

    def test_static_routes(self):
        self.assertEqual(200, self.client.get("/").status_code)
        self.assertEqual(200, self.client.get("/resume.html").status_code)
        self.assertEqual(200, self.client.get("/jobs_slim.json").status_code)


if __name__ == "__main__":
    unittest.main()
