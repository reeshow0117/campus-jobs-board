#!/usr/bin/env python3
"""秋招平台的简历生成 API；默认只处理浏览器当次提交的候选人资料。

公开模式不加载 xiao 的私人资料库，也不接受匿名用户访问私人资料。
本机单人模式需 QIUZHAO_PRIVATE_VAULT=1 且只绑定 127.0.0.1；不要反向代理此模式。
生产模式需先接入身份认证、限流与用量控制，再开放 LLM 接口。
"""
import argparse
import base64
import sqlite3
import binascii
import os
import re
import sys
import tempfile
from typing import Literal

if __package__:
    from . import access, llm, resume_gen, resume_pdf, vault_loader
else:  # 兼容 python agent/server.py 启动方式
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import access
    import llm
    import resume_gen
    import resume_pdf
    import vault_loader

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
VAULT_DIR = os.environ.get("QIUZHAO_VAULT", os.path.join(ROOT, "简历资料库"))
DIST_DIR = os.path.join(ROOT, "dist")
WEB_DIR = os.path.join(ROOT, "web")
PHOTO_PATH = os.environ.get("QIUZHAO_RESUME_PHOTO", os.path.join(BASE, "profiles", "xiao", "photo.png"))
PRIVATE_VAULT = os.environ.get("QIUZHAO_PRIVATE_VAULT") == "1"
ACCESS_DB = os.environ.get("QIUZHAO_ACCESS_DB", "")
MAX_JD_LEN = 8000
_cache = {}

app = FastAPI(title="秋招简历定制", docs_url=None, redoc_url=None)
# 未配置白名单时不允许跨域，供同域反代使用；localhost 仅在本机调试。
_origins = [s.strip() for s in os.environ.get("QIUZHAO_CORS", "").split(",") if s.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "Authorization"])


class InviteReq(BaseModel):
    invite_code: str = Field(min_length=32, max_length=128)


class Candidate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    edu: str = Field(default="", max_length=100)
    year: str = Field(default="", max_length=60)
    expect_job: str = Field(default="", max_length=100)
    expect_city: str = Field(default="", max_length=60)
    contact: str = Field(default="", max_length=180)


class Material(BaseModel):
    id: str = Field(pattern=r"^[ESPJAV]\d{1,3}$")
    org: str = Field(min_length=1, max_length=120)
    role: str = Field(default="", max_length=160)
    period: str = Field(default="", max_length=80)
    body: str = Field(min_length=1, max_length=4000)
    strength: str = Field(default="核心", max_length=20)
    directions: list[str] = Field(default_factory=list, max_length=12)
    usage: str = Field(default="", max_length=1000)


class ResumeReq(BaseModel):
    company: str = Field(default="", max_length=100)
    title: str = Field(default="", max_length=200)
    jd: str = Field(default="", max_length=MAX_JD_LEN)
    source: Literal["browser", "local_vault"] = "browser"
    profile: Candidate | None = None
    materials: list[Material] = Field(default_factory=list, max_length=40)


class PdfReq(BaseModel):
    markdown: str = Field(min_length=10, max_length=30000)
    source: Literal["browser", "local_vault"] = "browser"
    profile: Candidate | None = None
    materials: list[Material] = Field(default_factory=list, max_length=40)
    photo_data_url: str | None = Field(default=None, max_length=2_800_000)


def private_allowed(request: Request):
    """私人库仅在显式开启且客户端确为本机时可访问。绝不可反代公开此端口。"""
    return PRIVATE_VAULT and request.client is not None and request.client.host in ("127.0.0.1", "::1")


def access_store():
    if not ACCESS_DB or not os.path.isfile(ACCESS_DB):
        raise HTTPException(503, "邀请制尚未启用；生成接口保持关闭")
    return access.AccessStore(ACCESS_DB)


def deny_access(exc):
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    raise HTTPException(exc.status, str(exc), headers=headers) from exc


def require_user(request):
    # 本机单人模式沿用本机访问限定；公网模式必须持有已兑换的一次性邀请会话。
    if private_allowed(request):
        return None, None
    store = access_store()
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "请先使用邀请码登录")
    try:
        return store, store.user(header[7:])
    except access.AccessError as exc:
        deny_access(exc)
    except sqlite3.Error as exc:
        raise HTTPException(503, "访问控制暂不可用") from exc


def limit_request(store, user_id):
    if store is None:
        return
    try:
        store.consume(user_id, "request")
    except access.AccessError as exc:
        deny_access(exc)
    except sqlite3.Error as exc:
        raise HTTPException(503, "访问控制暂不可用") from exc


def get_private_materials():
    if "materials" not in _cache:
        basic, materials = vault_loader.load_vault(VAULT_DIR)
        _cache.update(basic=basic, materials=materials)
    return _cache["basic"], _cache["materials"]


def candidate_input(source, profile, materials, request):
    if source == "local_vault":
        if not private_allowed(request):
            raise HTTPException(403, "私人资料库仅供本机单人模式使用")
        basic, saved = get_private_materials()
        return {"name": basic.get("姓名", ""), "contact": " / ".join(
            x for x in [basic.get("电话", ""), basic.get("邮箱", "")] if x)}, saved
    if profile is None or not materials:
        raise HTTPException(400, "请先填写姓名和经历素材；平台不会读取其他人的资料库")
    if sum(len(item.body) for item in materials) > 50000:
        raise HTTPException(400, "经历素材总字数超过 5 万字，请精简后重试")
    data = profile.model_dump()
    selected = {}
    for item in materials:
        if item.id in selected:
            raise HTTPException(400, "资料编号重复，请检查经历母库")
        selected[item.id] = item.model_dump()
    if not any(mid.startswith("E") for mid in selected):
        raise HTTPException(400, "请至少填写一条教育经历")
    return data, selected


def validate_photo(data_url):
    if not data_url:
        return None
    m = re.fullmatch(r"data:image/(jpeg|png);base64,([A-Za-z0-9+/=]+)", data_url)
    if not m:
        raise HTTPException(400, "照片仅支持 JPG/PNG，且大小不超过 2 MB")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except binascii.Error as exc:
        raise HTTPException(400, "照片内容无效") from exc
    if len(raw) > 2_000_000 or len(raw) < 100 or not (
        raw.startswith(b"\xff\xd8\xff") or raw.startswith(b"\x89PNG\r\n\x1a\n")
    ):
        raise HTTPException(400, "照片仅支持 JPG/PNG，且大小不超过 2 MB")
    return raw


@app.get("/api/capabilities")
def capabilities(request: Request):
    return {"private_vault": private_allowed(request), "pdf": True,
            "invite_required": not private_allowed(request), "llm": llm.is_configured()}


@app.post("/api/invite/redeem")
def redeem_invite(req: InviteReq):
    store = access_store()
    try:
        quota = int(os.environ.get("QIUZHAO_MODEL_DAILY_LIMIT", "30"))
        if not 0 <= quota <= 10000:
            raise ValueError("invalid quota")
        session = store.redeem(req.invite_code, quota)
        return {"access_token": session, "token_type": "bearer", "expires_in": 30 * 86400}
    except access.AccessError as exc:
        deny_access(exc)
    except (ValueError, sqlite3.Error) as exc:
        raise HTTPException(503, "访问控制暂不可用") from exc


@app.get("/api/quota")
def quota_status(request: Request):
    store, user_id = require_user(request)
    if store is None:
        return {"private_local_mode": True}
    try:
        return store.quota(user_id)
    except access.AccessError as exc:
        deny_access(exc)
    except sqlite3.Error as exc:
        raise HTTPException(503, "访问控制暂不可用") from exc


@app.post("/api/resume")
def gen_resume(req: ResumeReq, request: Request):
    store, user_id = require_user(request)
    limit_request(store, user_id)
    if not req.jd.strip() and not req.title.strip():
        raise HTTPException(400, "请提供岗位名称或 JD 全文")
    profile, materials = candidate_input(req.source, req.profile, req.materials, request)
    if not llm.is_configured():
        raise HTTPException(503, "当前未配置简历生成服务")
    def charge():
        store.consume(user_id, "model")

    token = llm.charge_attempt.set(charge if store is not None else None)
    try:
        md = resume_gen.llm_chain(profile, materials, req.company, req.title,
                                  req.jd.strip() or req.title.strip())
    except access.AccessError as exc:
        deny_access(exc)
    except sqlite3.Error as exc:
        raise HTTPException(503, "访问控制暂不可用") from exc
    except llm.LLMError as exc:
        raise HTTPException(502, "模型生成失败，请稍后重试") from exc
    finally:
        llm.charge_attempt.reset(token)
    warnings = resume_gen.verify_resume(md, materials)
    # 不用只有问题清单的 prompt 重新生成：失去原始素材的重试会凭空编造。
    return {"markdown": md, "warnings": warnings}


@app.post("/api/resume_pdf")
def gen_pdf(req: PdfReq, request: Request):
    store, user_id = require_user(request)
    limit_request(store, user_id)
    profile, materials = candidate_input(req.source, req.profile, req.materials, request)
    warnings = resume_gen.verify_resume(req.markdown, materials)
    if warnings:
        raise HTTPException(422, {"message": "溯源未通过，拒绝导出，请逐条检查", "warnings": warnings})
    image = None if req.source == "local_vault" else validate_photo(req.photo_data_url)
    if req.source == "browser" and image is None:
        raise HTTPException(400, "请先上传证件照，正式 PDF 必须带照片")
    if req.source == "local_vault" and not os.path.isfile(PHOTO_PATH):
        raise HTTPException(400, "本机私人资料库缺少证件照")
    temporary = []
    try:
        if image:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(image)
                photo_path = tmp.name
                temporary.append(photo_path)
        elif req.source == "local_vault" and os.path.isfile(PHOTO_PATH):
            photo_path = PHOTO_PATH
        else:
            photo_path = None
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            out = tmp.name
            temporary.append(out)
        resume_pdf.md_to_pdf(req.markdown, out, photo_path=photo_path)
    except (ValueError, RuntimeError) as exc:
        for path in temporary:
            if os.path.exists(path):
                os.unlink(path)
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        for path in temporary:
            if os.path.exists(path):
                os.unlink(path)
        raise HTTPException(500, "PDF 生成失败，请稍后重试") from exc
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "", profile.get("name", ""))[:30] or "候选人"
    return FileResponse(out, media_type="application/pdf", filename=f"{safe_name}-定制简历.pdf",
                        background=BackgroundTask(lambda: [os.unlink(p) for p in temporary if os.path.exists(p)]))


@app.post("/api/reload")
def reload_vault(request: Request):
    if not private_allowed(request):
        raise HTTPException(403, "私人资料库仅供本机使用")
    _cache.clear()
    _, materials = get_private_materials()
    return {"materials": len(materials)}


@app.get("/")
def index():
    return FileResponse(os.path.join(DIST_DIR, "index.html"))


@app.get("/resume.html")
def resume_page():
    return FileResponse(os.path.join(WEB_DIR, "resume.html"))


@app.get("/jobs_slim.json")
def jobs_slim():
    path = os.path.join(DIST_DIR, "jobs_slim.json")
    if not os.path.isfile(path):
        raise HTTPException(404, "岗位索引尚未生成")
    return FileResponse(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if args.host not in ("127.0.0.1", "::1"):
        ap.error("服务只允许绑定本机回环地址；公网必须经 HTTPS 反向代理且通过用户确认")
    if not PRIVATE_VAULT and (not ACCESS_DB or not os.path.isfile(ACCESS_DB)):
        ap.error("邀请制未初始化：先在仓库外初始化 QIUZHAO_ACCESS_DB，服务保持关闭")
    resume_pdf.register_fonts()
    if PRIVATE_VAULT:
        _, mats = get_private_materials()
        print(f"本地私人库：{len(mats)} 条素材；不要通过公网反代此端口")
    if not llm.is_configured():
        print("未配置 LLM，生成接口将返回 503")
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
