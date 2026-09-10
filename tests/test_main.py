"""core.cli：命令分发与结果写回 SessionState。"""

import asyncio
from collections.abc import Coroutine
from types import SimpleNamespace
from typing import Any

from core import cli
from core.ui.commands import SessionState


def test_handle_command_pass_for_normal_input() -> None:
    state = SessionState()
    assert asyncio.run(cli.handle_command("写个 hello world", state)) == "pass"


def test_handle_command_unknown(capsys) -> None:
    state = SessionState()
    assert asyncio.run(cli.handle_command("/nope", state)) == "continue"
    assert "未知命令" in capsys.readouterr().out


def test_handle_command_help_continues() -> None:
    state = SessionState()
    assert asyncio.run(cli.handle_command("/help", state)) == "continue"


def test_handle_command_exit_breaks() -> None:
    state = SessionState()
    assert asyncio.run(cli.handle_command("/exit", state)) == "break"


def test_apply_result_updates_state(monkeypatch) -> None:
    state = SessionState(session_id="sid-1")
    history = [SimpleNamespace(parts=[])]
    new_msgs = [SimpleNamespace(parts=[])]
    result = SimpleNamespace(
        all_messages=lambda: history,
        new_messages=lambda: new_msgs,
        usage=SimpleNamespace(input_tokens=5, output_tokens=7),
    )

    appended: list = []
    monkeypatch.setattr(cli, "api_call_log", [SimpleNamespace(model="m")])
    monkeypatch.setattr(cli, "append_messages", lambda sid, msgs: appended.append((sid, msgs)))

    cli.apply_result(state, result)

    assert state.history is history
    assert state.input_tokens == 5
    assert state.output_tokens == 7
    assert len(state.last_api_calls) == 1
    assert appended == [("sid-1", new_msgs)]


def _raise_after_close(exc: BaseException):
    def _raise(coro: Coroutine[Any, Any, Any]) -> None:
        coro.close()
        raise exc

    return _raise


def test_main_handles_keyboard_interrupt(monkeypatch) -> None:
    monkeypatch.setattr(cli.asyncio, "run", _raise_after_close(KeyboardInterrupt()))
    cli.main()  # 不应向外抛


def test_main_handles_eof(monkeypatch) -> None:
    monkeypatch.setattr(cli.asyncio, "run", _raise_after_close(EOFError()))
    cli.main()  # 不应向外抛
