"""只输出可公开的前端路由配置，禁止序列化服务端环境变量。"""
import json
import os
from urllib.parse import urlsplit


def public_origin(value):
    if not value:
        return ""
    value = value.rstrip("/")
    url = urlsplit(value)
    local = url.hostname in ("127.0.0.1", "localhost", "::1")
    if (not url.hostname or url.username or url.password or url.path or url.query or url.fragment
            or not (url.scheme == "https" or (url.scheme == "http" and local))):
        raise ValueError("QIUZHAO_PUBLIC_API_URL 必须是 HTTPS 根地址（HTTP 仅限本机）")
    return value


def javascript(dashboard_url=None):
    config = {
        "api_base": public_origin(os.environ.get("QIUZHAO_PUBLIC_API_URL", "")),
        "dashboard_url": dashboard_url or "https://campus-jobs-board.pages.dev/",
    }
    return "window.QIUZHAO_CONFIG = " + json.dumps(config, ensure_ascii=True) + ";\n"
