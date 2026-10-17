"""core.agent.reminders：system-reminder 文案拼装。"""

import os
from pathlib import Path

from core.agent.file_state import ReadFileState
from core.agent.reminders import build_reminder_text


def test_no_stale_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("x", encoding="utf-8")
    state = ReadFileState()
    state.record(str(path), "x")
    assert build_reminder_text(state) is None


def test_stale_files_produce_tagged_reminder(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("1", encoding="utf-8")
    b.write_text("2", encoding="utf-8")
    state = ReadFileState()
    state.record(str(a), "1")
    state.record(str(b), "2")
    a.write_text("1!", encoding="utf-8")
    st = a.stat()
    os.utime(a, (st.st_atime, st.st_mtime + 5))

    text = build_reminder_text(state)
    assert text is not None
    assert text.startswith("<system-reminder>")
    assert text.endswith("</system-reminder>")
    # 只列过期的那个文件
    assert str(a) in text
    assert str(b) not in text
    assert "read_file" in text
