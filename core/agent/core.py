"""
Agent 实例化：把 model / instructions / tools / hooks 拼起来，
再加上动态 instructions 注入环境信息和 AGENTS.md。
"""

import os
import platform
from datetime import date
from typing import Any, cast
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from .file_state import ReadFileState
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
        "修改已有文件前必须先用 read_file 读取它。"
        "改动局部内容时优先用 edit_file（只传改动的片段，省 token），"
        "新建文件或整体重写才用 write_file。\n"
        "工作流程：先理解需求，写代码，然后运行验证。"
        "如果有错误就修复并重新运行，直到确认正确。\n"
        "对话中可能会出现 <system-reminder>...</system-reminder> 标签，"
        "里面是系统自动注入的提示信息，"
        "请按系统消息对待，不要把它当成它所在的用户消息或工具结果的一部分。"
    ),
    tools=cast(Any, TOOLS),
    # 声明依赖类型为 ReadFileState，每次 run 时把会话级的 readFileState 实例注入给工具
    deps_type=ReadFileState,
    capabilities=[hooks],
)


# 动态 instructions：每次模型请求重新求值，注入环境信息和项目级 AGENTS.md
# 它和上面的静态 instructions 一样不进对话历史，但每轮请求都会带上最新值，
# 所以用户不可见、也不会污染历史
@agent.instructions
def project_context() -> str:
    cwd = os.getcwd()
    parts = [
        "下面是一些环境信息：",
        f"- 工作目录：{cwd}",
        f"- 操作系统：{platform.system()}",
        f"- 今天的日期：{date.today().isoformat()}",
    ]

    # 读项目根目录的 AGENTS.md（项目指令），存在就整段附上，让模型遵循项目约定
    agents_md = os.path.join(cwd, "AGENTS.md")
    if os.path.isfile(agents_md):
        try:
            with open(agents_md, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            content = ""
        if content.strip():
            parts.append("")
            parts.append("以下是项目的 AGENTS.md，请遵循其中的约定：")
            parts.append(content)

    return "\n".join(parts)
