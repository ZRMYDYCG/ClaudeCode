"""core.agent.tools：读写文件与执行命令。"""

from pathlib import Path

from core.agent.tools import read_file, run_command, write_file


def test_read_file_returns_content(tmp_path: Path) -> None:
    path = tmp_path / "hello.txt"
    path.write_text("hello world", encoding="utf-8")
    assert read_file(str(path)) == "hello world"


def test_read_file_missing_returns_error(tmp_path: Path) -> None:
    path = tmp_path / "missing.txt"
    assert read_file(str(path)) == f"错误：文件 {path} 不存在"


def test_write_file_creates_and_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "out.txt"
    assert write_file(str(path), "first") == f"已写入 {path}"
    assert path.read_text(encoding="utf-8") == "first"

    assert write_file(str(path), "second") == f"已写入 {path}"
    assert path.read_text(encoding="utf-8") == "second"


def test_run_command_stdout() -> None:
    assert run_command("echo hello") == "hello\n"


def test_run_command_nonzero_includes_stderr() -> None:
    output = run_command("echo fail >&2; exit 1")
    assert "[错误]" in output
    assert "fail" in output


def test_run_command_empty_stdout() -> None:
    assert run_command("true") == "(无输出)"


def test_run_command_timeout(monkeypatch) -> None:
    import subprocess

    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="sleep", timeout=10)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    assert run_command("sleep 999") == "[错误] 命令执行超时（10秒）"
