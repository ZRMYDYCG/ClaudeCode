"""
Agent 实例化：把 model / instructions / tools / hooks 拼起来。
"""

import os
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from .hooks import hooks
from .tools import TOOLS

load_dotenv()

# 从环境变量读取 API Key / Base URL（OpenAI 兼容接口）
API_KEY = os.environ.get("API_KEY")
if not API_KEY:
    raise RuntimeError("请先设置环境变量 API_KEY")

BASE_URL = os.environ.get("BASE_URL")
if not BASE_URL:
    raise RuntimeError("请先设置环境变量 BASE_URL")


def _normalize_openai_base_url(url: str) -> str:
    """
    OpenAI SDK 会自己拼 /chat/completions；若 .env 里写了完整 path，去掉末尾这段。
    """
    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/completions"):
        if path.endswith(suffix):
            path = path[: -len(suffix)] or "/"
            break
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


MODEL_NAME = os.environ.get("MODEL_NAME", "deepseek-v4-flash")

model = OpenAIChatModel(
    MODEL_NAME,
    provider=OpenAIProvider(base_url=_normalize_openai_base_url(BASE_URL), api_key=API_KEY),
)

agent = Agent(
    model,
    instructions=(
        "你是一个编程助手。你可以读写文件和执行命令来帮用户完成编程任务。\n"
        "工作流程：先理解需求，写代码，然后运行验证。"
        "如果有错误就修复并重新运行，直到确认正确。"
    ),
    tools=TOOLS,
    capabilities=[hooks],
)
