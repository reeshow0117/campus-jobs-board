"""LLM 客户端封装（OpenAI 兼容接口，仅用标准库）

凭据与地址全部从环境变量读取（C6）：
  QIUZHAO_LLM_API_KEY   API 密钥（不配则纯规则模式，整个系统照常可用）
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


# 服务端在当前请求中注入按用户计费回调；本机离线 CLI 不设置该回调。
charge_attempt = ContextVar("charge_model_attempt", default=None)


class LLMError(Exception):
    """LLM 调用失败（含超时、网络错误、非 200、响应格式非法）。"""


def is_configured():
    return bool(os.environ.get("QIUZHAO_LLM_API_KEY") and os.environ.get("QIUZHAO_LLM_BASE_URL"))


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

    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }).encode("utf-8")

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
            meter = charge_attempt.get()
            if meter is not None:
                meter()  # 重试也计入额度；先扣额度再触发外部计费请求。
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last_err = LLMError(f"HTTP {e.code}: {e.read()[:200]!r}")
            if 400 <= e.code < 500:
                raise last_err  # 客户端错误重试无意义
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError,
                KeyError, IndexError) as e:
            last_err = LLMError(f"{type(e).__name__}: {e}")
        if attempt < retries:
            time.sleep(2 ** attempt + random.random())  # 指数退避 + 抖动
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
