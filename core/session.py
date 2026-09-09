"""
会话持久化：把对话历史写成 jsonl 文件，支持扫描和恢复历史会话。
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_core import to_jsonable_python

# 所有会话记录的根目录
STORAGE_ROOT = Path.home() / ".zrcoder" / "projects"


def sanitize_path(path: str) -> str:
    """
    把项目绝对路径转码成合法的目录名：非字母数字字符一律换成 -
    """
    return re.sub(r"[^a-zA-Z0-9]", "-", path)


def project_dir() -> Path:
    """
    当前项目（工作目录）对应的会话存储目录。
    """
    return STORAGE_ROOT / sanitize_path(str(Path.cwd()))


def new_session_id() -> str:
    return str(uuid.uuid4())


def session_file(session_id: str) -> Path:
    return project_dir() / f"{session_id}.jsonl"


def append_messages(session_id: str, messages: Any) -> None:
    """
    把本轮新增的消息追加到会话文件末尾，一行一条。
    """
    if not session_id:
        return
    path = session_file(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(to_jsonable_python(msg), ensure_ascii=False) + "\n")


def load_history(session_id: str) -> list[Any]:
    """
    读取整个会话文件，把每行 JSON 还原成 SDK 的消息对象列表。
    """
    lines = session_file(session_id).read_text(encoding="utf-8").splitlines()
    return ModelMessagesTypeAdapter.validate_python([json.loads(line) for line in lines])


def first_prompt(path: Path) -> str:
    """
    只读文件第一行，提取首条用户输入作为这个会话的摘要。
    """
    with open(path, encoding="utf-8") as f:
        head = f.readline()
    if not head:
        return "(空会话)"
    msg = json.loads(head)
    for part in msg.get("parts", []):
        if part.get("part_kind") == "user-prompt":
            return str(part.get("content", ""))
    return "(空会话)"


def list_sessions() -> list[tuple[str, datetime, str]]:
    """
    扫描当前项目的所有会话文件，按修改时间从新到旧返回
    (session_id, 修改时间, 首条用户输入) 列表。
    """
    if not project_dir().exists():
        return []
    files = sorted(
        project_dir().glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [(p.stem, datetime.fromtimestamp(p.stat().st_mtime), first_prompt(p)) for p in files]
