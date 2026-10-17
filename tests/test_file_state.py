"""core.agent.file_state：会话级读取状态与过期检测。"""

import os
from pathlib import Path

from core.agent.file_state import ReadFileState


def _bump_mtime(path: Path) -> None:
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 5))


def test_stale_paths_empty_when_untouched(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("x", encoding="utf-8")
    state = ReadFileState()
    state.record(str(path), "x")
    assert state.stale_paths() == []


def test_stale_paths_detects_external_modification(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("x", encoding="utf-8")
    state = ReadFileState()
    state.record(str(path), "x")
    path.write_text("y", encoding="utf-8")
    _bump_mtime(path)
    assert state.stale_paths() == [str(path)]
    # 模型重读后 record() 刷新 timestamp，就不再过期
    state.record(str(path), "y")
    assert state.stale_paths() == []


def test_stale_paths_ignores_deleted_files(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("x", encoding="utf-8")
    state = ReadFileState()
    state.record(str(path), "x")
    path.unlink()
    assert state.stale_paths() == []


def test_stale_paths_ignores_own_writes(tmp_path: Path) -> None:
    # 模型自己的 edit / write 通过 record() 刷新 timestamp，绝不能算成被外部改过
    path = tmp_path / "a.txt"
    path.write_text("x", encoding="utf-8")
    state = ReadFileState()
    state.record(str(path), "x")
    path.write_text("y", encoding="utf-8")
    state.record(str(path), "y")
    assert state.stale_paths() == []
