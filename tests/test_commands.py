"""core.ui.commands：会话状态、斜杠命令与 part 格式化。"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from core import permissions
from core.ui.commands import (
    COMMANDS,
    SessionState,
    _format_part_line,
    _summary_line,
    _truncate,
    cmd_api_detail,
    cmd_exit,
    cmd_help,
    cmd_new,
    cmd_resume,
    cmd_status,
)


def test_truncate_short() -> None:
    assert _truncate("abc") == "abc"


def test_truncate_long() -> None:
    text = "x" * 150
    result = _truncate(text, 120)
    assert result.endswith("...")
    assert len(result) == 123  # 120 + "..."


def test_truncate_escapes_markup() -> None:
    # rich.escape 会给 [ 加反斜杠，避免被当成 markup
    assert _truncate("[bold]hi") == r"\[bold]hi"


def test_format_part_line_kinds() -> None:
    assert "user" in (
        _format_part_line(SimpleNamespace(part_kind="user-prompt", content="hi")) or ""
    )
    assert "thinking" in (
        _format_part_line(SimpleNamespace(part_kind="thinking", content="hmm")) or ""
    )
    assert "assistant" in (_format_part_line(SimpleNamespace(part_kind="text", content="ok")) or "")
    assert _format_part_line(SimpleNamespace(part_kind="text", content="  ")) is None
    tool_call = _format_part_line(
        SimpleNamespace(part_kind="tool-call", tool_name="read_file", args='{"path":"a"}')
    )
    assert tool_call is not None and "read_file" in tool_call
    tool_return = _format_part_line(
        SimpleNamespace(part_kind="tool-return", tool_name="read_file", content="data")
    )
    assert tool_return is not None and "tool_return" in tool_return
    retry = _format_part_line(
        SimpleNamespace(part_kind="retry-prompt", tool_name="read_file", content="retry")
    )
    assert retry is not None and "tool_retry" in retry
    assert _format_part_line(SimpleNamespace(part_kind="unknown")) is None


def test_cmd_new_clears_state() -> None:
    permissions.state.session_allowed.add("run_command")
    state = SessionState(
        history=["a"],
        input_tokens=10,
        output_tokens=20,
        model_name="m",
        last_api_calls=["call"],
        session_id="old-id",
    )
    assert cmd_new(state) is True
    assert state.history == []
    assert state.input_tokens == 0
    assert state.output_tokens == 0
    assert state.last_api_calls == []
    assert state.model_name == "m"
    assert state.session_id != "old-id"
    assert state.session_id
    assert permissions.state.session_allowed == set()


def test_cmd_exit_returns_false() -> None:
    assert cmd_exit(SessionState()) is False


def test_cmd_help_and_status(capsys) -> None:
    state = SessionState(model_name="test-model", input_tokens=1, output_tokens=2)
    assert cmd_help(state) is True
    assert cmd_status(state) is True
    out = capsys.readouterr().out
    assert "/help" in out or "help" in out
    assert "test-model" in out
    assert permissions.state.mode in out
    assert "1" in out and "2" in out


def test_cmd_api_detail_empty(capsys) -> None:
    assert cmd_api_detail(SessionState()) is True
    assert "还没有任何模型调用记录" in capsys.readouterr().out


def test_cmd_api_detail_with_calls(capsys) -> None:
    call = SimpleNamespace(
        model="m",
        messages_count=2,
        last_part=SimpleNamespace(part_kind="user-prompt", content="hi"),
        tools=["read_file"],
        finish_reason="stop",
        parts_kinds=["text"],
        input_tokens=3,
        output_tokens=4,
    )
    state = SessionState(last_api_calls=[call])
    assert cmd_api_detail(state) is True
    out = capsys.readouterr().out
    assert "Call #1" in out
    assert "read_file" in out
    assert "stop" in out


def test_commands_registry() -> None:
    assert set(COMMANDS) == {"new", "resume", "status", "api-detail", "help", "exit"}
    for name, cmd in COMMANDS.items():
        assert cmd.name == name
        assert callable(cmd.handler)


def test_summary_line_truncates() -> None:
    mtime = datetime(2026, 9, 9, 12, 30)
    line = _summary_line(mtime, "hello " * 20)
    assert line.startswith("09-09 12:30")
    assert line.endswith("...")


def test_cmd_resume_empty(monkeypatch, capsys) -> None:
    monkeypatch.setattr("core.ui.commands.session.list_sessions", lambda: [])
    assert asyncio.run(cmd_resume(SessionState())) is True
    assert "还没有历史会话" in capsys.readouterr().out


def test_cmd_resume_cancel(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.ui.commands.session.list_sessions",
        lambda: [("sid", datetime(2026, 1, 1, 0, 0), "hi")],
    )
    select = MagicMock()
    select.ask_async = AsyncMock(return_value=None)
    monkeypatch.setattr("core.ui.commands.questionary.select", lambda *a, **k: select)
    state = SessionState(session_id="old")
    assert asyncio.run(cmd_resume(state)) is True
    assert state.session_id == "old"


def test_cmd_resume_loads_history(monkeypatch, capsys) -> None:
    permissions.state.session_allowed.add("write_file")
    monkeypatch.setattr(
        "core.ui.commands.session.list_sessions",
        lambda: [("abcdef12-xxxx", datetime(2026, 1, 1, 0, 0), "hello")],
    )
    select = MagicMock()
    select.ask_async = AsyncMock(return_value="abcdef12-xxxx")
    monkeypatch.setattr("core.ui.commands.questionary.select", lambda *a, **k: select)

    response = SimpleNamespace(
        kind="response",
        usage=SimpleNamespace(input_tokens=3, output_tokens=4),
        parts=[SimpleNamespace(part_kind="text", content="ok")],
    )
    monkeypatch.setattr(
        "core.ui.commands.session.load_history",
        lambda _sid: [response],
    )
    monkeypatch.setattr("core.ui.commands.print_part", lambda _part: None)

    state = SessionState()
    assert asyncio.run(cmd_resume(state)) is True
    assert state.session_id == "abcdef12-xxxx"
    assert state.history == [response]
    assert state.input_tokens == 3
    assert state.output_tokens == 4
    assert permissions.state.session_allowed == set()
    assert "已恢复会话 abcdef12" in capsys.readouterr().out
