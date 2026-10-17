"""core.agent.tools：读、编辑、写文件与执行命令。"""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic_ai.exceptions import ModelRetry

from core.agent.file_state import ReadFileState
from core.agent.tools import edit_file, read_and_register, read_file, run_command, write_file


def _ctx() -> SimpleNamespace:
    """工具只用到 ctx.deps，用 SimpleNamespace 顶替 RunContext 注入一份全新状态。"""
    return SimpleNamespace(deps=ReadFileState())


def test_read_file_returns_numbered_content_and_records(tmp_path: Path) -> None:
    path = tmp_path / "hello.txt"
    path.write_text("hello world", encoding="utf-8")
    ctx = _ctx()
    assert read_file(ctx, str(path)) == "1\thello world"
    record = ctx.deps.get(str(path))
    assert record is not None
    assert record["content"] == "hello world"


def test_read_file_offset_limit_slices(tmp_path: Path) -> None:
    path = tmp_path / "many.txt"
    path.write_text("\n".join(f"line{i}" for i in range(1, 11)), encoding="utf-8")
    out = read_file(_ctx(), str(path), offset=3, limit=2)
    assert out.splitlines() == ["3\tline3", "4\tline4"]


def test_read_file_truncates_and_hints_offset(tmp_path: Path) -> None:
    path = tmp_path / "big.txt"
    path.write_text("\n".join(f"line{i}" for i in range(1, 2101)), encoding="utf-8")
    out = read_file(_ctx(), str(path))
    assert "2000\tline2000" in out
    assert "line2001" not in out
    assert "还有 100 行未显示" in out
    assert "offset=2001" in out


def test_read_file_offset_beyond_end_warns(tmp_path: Path) -> None:
    path = tmp_path / "short.txt"
    path.write_text("one\ntwo", encoding="utf-8")
    assert "没有内容可读" in read_file(_ctx(), str(path), offset=99)


def test_read_file_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    assert "空文件" in read_file(_ctx(), str(path))


def test_read_file_missing_raises_model_retry(tmp_path: Path) -> None:
    path = tmp_path / "missing.txt"
    with pytest.raises(ModelRetry, match="不存在"):
        read_file(_ctx(), str(path))


def test_read_file_directory_raises_model_retry(tmp_path: Path) -> None:
    with pytest.raises(ModelRetry, match="目录"):
        read_file(_ctx(), str(tmp_path))


def test_read_file_permission_raises_model_retry() -> None:
    with (
        patch("builtins.open", side_effect=PermissionError()),
        pytest.raises(ModelRetry, match="没有权限"),
    ):
        read_file(_ctx(), "/secret.txt")


def test_read_file_binary_returns_error(tmp_path: Path) -> None:
    path = tmp_path / "bin.dat"
    path.write_bytes(b"\xff\xfe\x00\x01")
    assert "不是文本文件" in read_file(_ctx(), str(path))


def test_read_and_register_records_range(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("one\ntwo", encoding="utf-8")
    state = ReadFileState()
    assert read_and_register(state, str(path)) == "1\tone\n2\ttwo"
    record = state.get(str(path))
    assert record is not None
    assert record["content"] == "one\ntwo"
    assert record["offset"] == 1
    assert record["limit"] is None


def test_read_file_dedups_unchanged_file(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("alpha", encoding="utf-8")
    ctx = _ctx()
    assert read_file(ctx, str(path)) == "1\talpha"
    assert "不必重复读取" in read_file(ctx, str(path))


def test_read_file_rereads_after_change(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("alpha", encoding="utf-8")
    ctx = _ctx()
    read_file(ctx, str(path))
    path.write_text("beta\ngamma", encoding="utf-8")
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 5))
    assert read_file(ctx, str(path)) == "1\tbeta\n2\tgamma"


def test_read_file_different_range_skips_dedup(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("one\ntwo\nthree", encoding="utf-8")
    ctx = _ctx()
    read_file(ctx, str(path), limit=1)
    assert "2\ttwo" in read_file(ctx, str(path))


def test_read_file_dedup_skips_after_edit(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("alpha\nbeta", encoding="utf-8")
    ctx = _ctx()
    read_file(ctx, str(path))
    edit_file(ctx, str(path), "beta", "GAMMA")
    assert read_file(ctx, str(path)) == "1\talpha\n2\tGAMMA"


def test_edit_file_requires_read_first(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("alpha", encoding="utf-8")
    with pytest.raises(ModelRetry, match="还没读过"):
        edit_file(_ctx(), str(path), "alpha", "ALPHA")


def test_edit_file_rejects_noop(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("alpha", encoding="utf-8")
    ctx = _ctx()
    read_file(ctx, str(path))
    with pytest.raises(ModelRetry, match="完全相同"):
        edit_file(ctx, str(path), "alpha", "alpha")


def test_edit_file_rejects_missing_old_string(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("alpha", encoding="utf-8")
    ctx = _ctx()
    read_file(ctx, str(path))
    with pytest.raises(ModelRetry, match="找不到"):
        edit_file(ctx, str(path), "nope", "x")


def test_edit_file_requires_unique_match(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("alpha\nalpha", encoding="utf-8")
    ctx = _ctx()
    read_file(ctx, str(path))
    with pytest.raises(ModelRetry, match="出现了 2 次"):
        edit_file(ctx, str(path), "alpha", "A")
    assert (
        edit_file(ctx, str(path), "alpha", "A", replace_all=True) == f"已编辑 {path}（替换 2 处）"
    )
    assert path.read_text(encoding="utf-8") == "A\nA"


def test_edit_file_replaces_single_occurrence(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("alpha\nbeta", encoding="utf-8")
    ctx = _ctx()
    read_file(ctx, str(path))
    assert edit_file(ctx, str(path), "beta", "BETA") == f"已编辑 {path}（替换 1 处）"
    assert path.read_text(encoding="utf-8") == "alpha\nBETA"
    assert edit_file(ctx, str(path), "BETA", "GAMMA") == f"已编辑 {path}（替换 1 处）"


def test_edit_file_rejects_modified_after_read(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("alpha", encoding="utf-8")
    ctx = _ctx()
    read_file(ctx, str(path))
    path.write_text("hacked", encoding="utf-8")
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 5))
    with pytest.raises(ModelRetry, match="被改动过"):
        edit_file(ctx, str(path), "hacked", "safe")


def test_edit_file_missing_file_raises_model_retry(tmp_path: Path) -> None:
    path = tmp_path / "code.txt"
    path.write_text("alpha", encoding="utf-8")
    ctx = _ctx()
    read_file(ctx, str(path))
    path.unlink()
    with pytest.raises(ModelRetry, match="已不存在"):
        edit_file(ctx, str(path), "alpha", "ALPHA")


def test_write_file_creates_and_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "out.txt"
    ctx = _ctx()
    assert write_file(ctx, str(path), "first") == f"已写入 {path}"
    assert path.read_text(encoding="utf-8") == "first"

    assert write_file(ctx, str(path), "second") == f"已写入 {path}"
    assert path.read_text(encoding="utf-8") == "second"


def test_write_file_overwrite_requires_read_first(tmp_path: Path) -> None:
    path = tmp_path / "out.txt"
    path.write_text("existing", encoding="utf-8")
    with pytest.raises(ModelRetry, match="覆盖前请先"):
        write_file(_ctx(), str(path), "new")


def test_write_file_missing_dir_raises_model_retry(tmp_path: Path) -> None:
    path = tmp_path / "nope" / "out.txt"
    with pytest.raises(ModelRetry, match="目录不存在"):
        write_file(_ctx(), str(path), "x")


def test_write_file_permission_raises_model_retry() -> None:
    with (
        patch("builtins.open", side_effect=PermissionError()),
        pytest.raises(ModelRetry, match="没有权限写入"),
    ):
        write_file(_ctx(), "/secret.txt", "x")


def test_write_file_oserror_returns_message() -> None:
    with patch("builtins.open", side_effect=OSError("disk full")):
        assert "写入" in write_file(_ctx(), "/x.txt", "x")
        assert "disk full" in write_file(_ctx(), "/x.txt", "x")


def test_run_command_stdout() -> None:
    assert run_command("echo hello") == "hello\n"


def test_run_command_nonzero_includes_stderr() -> None:
    output = run_command("echo fail >&2; exit 1")
    assert "[错误]" in output
    assert "fail" in output


def test_run_command_empty_stdout() -> None:
    assert run_command("true") == "(无输出)"


def test_run_command_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="sleep", timeout=10)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    assert run_command("sleep 999") == "[错误] 命令执行超时（10秒）"


def test_run_command_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def _raise_os(*_args, **_kwargs):
        raise OSError("no shell")

    monkeypatch.setattr(subprocess, "run", _raise_os)
    assert "无法执行命令" in run_command("echo hi")
