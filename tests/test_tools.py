"""core.agent.tools：读写文件与执行命令。"""

from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic_ai.exceptions import ModelRetry

from core.agent.tools import read_file, run_command, write_file


def test_read_file_returns_content(tmp_path: Path) -> None:
    path = tmp_path / "hello.txt"
    path.write_text("hello world", encoding="utf-8")
    assert read_file(str(path)) == "hello world"


def test_read_file_missing_raises_model_retry(tmp_path: Path) -> None:
    path = tmp_path / "missing.txt"
    with pytest.raises(ModelRetry, match="不存在"):
        read_file(str(path))


def test_read_file_directory_raises_model_retry(tmp_path: Path) -> None:
    with pytest.raises(ModelRetry, match="目录"):
        read_file(str(tmp_path))


def test_read_file_permission_raises_model_retry() -> None:
    with (
        patch("builtins.open", side_effect=PermissionError()),
        pytest.raises(ModelRetry, match="没有权限"),
    ):
        read_file("/secret.txt")


def test_read_file_binary_returns_error(tmp_path: Path) -> None:
    path = tmp_path / "bin.dat"
    path.write_bytes(b"\xff\xfe\x00\x01")
    assert "不是文本文件" in read_file(str(path))


def test_write_file_creates_and_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "out.txt"
    assert write_file(str(path), "first") == f"已写入 {path}"
    assert path.read_text(encoding="utf-8") == "first"

    assert write_file(str(path), "second") == f"已写入 {path}"
    assert path.read_text(encoding="utf-8") == "second"


def test_write_file_missing_dir_raises_model_retry(tmp_path: Path) -> None:
    path = tmp_path / "nope" / "out.txt"
    with pytest.raises(ModelRetry, match="目录不存在"):
        write_file(str(path), "x")


def test_write_file_permission_raises_model_retry() -> None:
    with (
        patch("builtins.open", side_effect=PermissionError()),
        pytest.raises(ModelRetry, match="没有权限写入"),
    ):
        write_file("/secret.txt", "x")


def test_write_file_oserror_returns_message() -> None:
    with patch("builtins.open", side_effect=OSError("disk full")):
        assert "写入" in write_file("/x.txt", "x")
        assert "disk full" in write_file("/x.txt", "x")


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
