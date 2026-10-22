"""LLM 客户端封装（OpenAI 兼容接口，仅用标准库）

凭据与地址全部从环境变量读取（C6）：
  QIUZHAO_LLM_API_KEY   API 密钥（未配置时网页生成接口返回 503）
  QIUZHAO_LLM_BASE_URL  接口地址，如 https://api.openai.com/v1
  QIUZHAO_LLM_MODEL     模型名

所有调用带显式超时、有限重试（指数退避 + 抖动），失败抛 LLMError 由上层降级（C4）。
"""
from contextvars import ContextVar
import json
import os
import random
import time
import urllib.request
import urllib.error
from urllib.parse import urlsplit


# 服务端在当前请求中注入按用户计费回调；本机离线 CLI 不设置该回调。
charge_attempt = ContextVar("charge_model_attempt", default=None)
deadline = ContextVar("model_deadline", default=None)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """模型凭据不能随上游重定向发送到其他主机。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_model(req, timeout):
    return urllib.request.build_opener(NoRedirect).open(req, timeout=timeout)


def remaining_timeout(timeout_s):
    end = deadline.get()
    if end is None:
        return timeout_s
    remaining = end - time.monotonic()
    if remaining <= 0:
        raise LLMError("生成已超时，请稍后重试或精简 JD 和素材")
    return min(timeout_s, remaining)


class LLMError(Exception):
    """LLM 调用失败（含超时、网络错误、非 200、响应格式非法）。"""

    def __init__(self, message, public_message=None):
        super().__init__(message)
        self.public_message = public_message or "模型生成失败，请稍后重试"


def is_configured():
    return bool(os.environ.get("QIUZHAO_LLM_API_KEY") and os.environ.get("QIUZHAO_LLM_BASE_URL")
                and os.environ.get("QIUZHAO_LLM_MODEL"))


def chat(prompt, timeout_s=30, retries=2, max_tokens=2000):
    """调用 chat completions，返回文本内容。失败抛 LLMError。

    重试策略：最多 retries 次重试，退避 2^i 秒 + 0~1s 抖动；
    4xx（客户端错误，如鉴权失败）不重试，直接抛错。
    """
    api_key = os.environ.get("QIUZHAO_LLM_API_KEY", "")
    base_url = os.environ.get("QIUZHAO_LLM_BASE_URL", "").rstrip("/")
    model = os.environ.get("QIUZHAO_LLM_MODEL", "")
    if not api_key or not base_url or not model:
        raise LLMError("LLM 未配置（缺 QIUZHAO_LLM_API_KEY / BASE_URL / MODEL）")
    parsed = urlsplit(base_url)
    local = parsed.hostname in ("127.0.0.1", "localhost", "::1")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname or (
            parsed.scheme != "https" and not (parsed.scheme == "http" and local)):
        raise LLMError("模型接口必须使用 HTTPS；仅本机模型服务允许 HTTP")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    # 当前 DeepSeek 默认开启思考；简历三步链使用非思考模式，避免预算耗在推理正文上。
    if parsed.hostname == "api.deepseek.com":
        payload["thinking"] = {"type": "disabled"}
    body = json.dumps(payload).encode("utf-8")

    last_err = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            base_url + "/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + api_key,
            },
            method="POST",
        )
        try:
            timeout = remaining_timeout(timeout_s)
            meter = charge_attempt.get()
            if meter is not None:
                meter()  # 重试也计入额度；先扣额度再触发外部计费请求。
            with open_model(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            remaining_timeout(timeout_s)
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                raise LLMError("模型输出被截断", "模型输出超出长度限制，请精简素材后重试")
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise LLMError("模型返回空内容，请检查模型配置")
            return content
        except urllib.error.HTTPError as e:
            messages = {
                401: "模型密钥无效，请联系管理员检查配置",
                403: "模型服务拒绝访问，请联系管理员检查权限",
                402: "模型账户余额不足，请联系管理员充值",
                429: "模型服务繁忙或达到调用限制，请稍后再试",
            }
            last_err = LLMError(f"模型接口返回 HTTP {e.code}", messages.get(e.code))
            e.close()
            if 400 <= e.code < 500:
                raise last_err  # 客户端错误重试无意义
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError,
                KeyError, IndexError, TypeError, AttributeError, UnicodeError, OSError) as e:
            last_err = LLMError(f"模型响应失败（{type(e).__name__}）")
        if attempt < retries:
            delay = 2 ** attempt + random.random()
            if remaining_timeout(delay + 0.1) < delay + 0.1:
                raise LLMError("生成已超时，请稍后重试或精简 JD 和素材")
            time.sleep(delay)
    raise last_err


def chat_json(prompt, timeout_s=30, retries=2):
    """调用 LLM 并解析 JSON 响应（容忍 ```json 包裹）。失败抛 LLMError。"""
    text = chat(prompt, timeout_s=timeout_s, retries=retries)
    text = text.strip()
    if text.startswith("```"):
        # 去掉 markdown 代码围栏
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMError(f"LLM 返回非 JSON: {e}; 原文前 200 字: {text[:200]!r}")
