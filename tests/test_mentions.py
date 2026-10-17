"""core.mentions：@ 文件引用的解析、注入与补全候选。"""

import os
from pathlib import Path

from core.agent.file_state import ReadFileState
from core.mentions import build_mention_messages, extract_at_mentions, list_candidate_files


def test_extract_at_mentions_tokens_in_order() -> None:
    paths = extract_at_mentions("先看 @core/cli.py 再看 @core/session.py")
    assert paths == ["core/cli.py", "core/session.py"]


def test_extract_at_mentions_dedupes_and_skips_non_paths() -> None:
    # 孤零零的 @ 后面没有路径字符，不算引用；邮箱的 @ 前面不是空白，也不算
    paths = extract_at_mentions("@a.py @b.py @a.py 结尾孤零零的 @ 不算，foo@bar.com 也不算")
    assert paths == ["a.py", "b.py"]


def test_build_mention_messages_registers_and_simulates_read(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("alpha", encoding="utf-8")
    state = ReadFileState()
    messages = build_mention_messages([str(path)], state)

    assert len(messages) == 2
    call_part = messages[0].parts[0]
    return_part = messages[1].parts[0]
    assert call_part.tool_name == "read_file"
    assert call_part.args_as_dict() == {"path": os.path.abspath(str(path))}
    assert return_part.tool_call_id == call_part.tool_call_id
    assert "1\talpha" in return_part.content
    # 登记进 readFileState，后续 edit 的先读后写校验直接通过
    record = state.get(str(path))
    assert record is not None
    assert record["content"] == "alpha"


def test_build_mention_messages_skips_missing_file(tmp_path: Path) -> None:
    missing = str(tmp_path / "nope.txt")
    state = ReadFileState()
    assert build_mention_messages([missing], state) == []
    assert state.get(missing) is None


def test_build_mention_messages_skips_directory(tmp_path: Path) -> None:
    state = ReadFileState()
    assert build_mention_messages([str(tmp_path)], state) == []
    assert state.get(str(tmp_path)) is None


def test_list_candidate_files_returns_relative_paths() -> None:
    files = list_candidate_files()
    assert isinstance(files, list)
    assert files
    assert all(not f.startswith("/") for f in files)
    # 测试从仓库根目录跑，本文件必然在候选里
    assert "core/mentions.py" in files
