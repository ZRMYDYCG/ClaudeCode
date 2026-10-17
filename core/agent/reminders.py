"""
system-reminder 文案：把 ReadFileState 里的过期文件拼成一条提醒文本的纯函数。

只做字符串拼装，不读写任何状态；注入时机由 hooks 的 before_model_request 决定。
模型重读后 record() 刷新 timestamp，同批文件自然不会被重复提醒。
"""

from __future__ import annotations

from .file_state import ReadFileState


def build_reminder_text(state: ReadFileState) -> str | None:
    """
    有过期文件就返回包在 <system-reminder> 标签里的提醒文本；
    什么都没变就返回 None，调用方据此完全不注入，不浪费请求内容。
    """
    stale = state.stale_paths()
    if not stale:
        return None
    lines = [
        "以下文件在本会话读取之后又被会话之外的东西改动过，你之前读到的内容已过期：",
        *[f"- {path}" for path in stale],
        "如果你接下来的操作依赖它们的内容，请先用 read_file 重新读取。",
    ]
    return "<system-reminder>\n" + "\n".join(lines) + "\n</system-reminder>"
