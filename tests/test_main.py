"""main：命令分发与结果写回 SessionState。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import main
from core.ui.commands import SessionState


def test_handle_command_pass_for_normal_input() -> None:
    state = SessionState()
    assert main.handle_command("写个 hello world", state) == "pass"


def test_handle_command_unknown(capsys) -> None:
    state = SessionState()
    assert main.handle_command("/nope", state) == "continue"
    assert "未知命令" in capsys.readouterr().out


def test_handle_command_help_continues() -> None:
    state = SessionState()
    assert main.handle_command("/help", state) == "continue"


def test_handle_command_exit_breaks() -> None:
    state = SessionState()
    assert main.handle_command("/exit", state) == "break"


def test_apply_result_updates_state_and_prints(monkeypatch) -> None:
    state = SessionState()
    history = [SimpleNamespace(parts=[])]
    new_msgs = [SimpleNamespace(parts=[])]
    result = SimpleNamespace(
        all_messages=lambda: history,
        new_messages=lambda: new_msgs,
        usage=SimpleNamespace(input_tokens=5, output_tokens=7),
    )

    printed: list = []
    monkeypatch.setattr(main, "print_agent_steps", lambda msgs: printed.append(msgs))
    monkeypatch.setattr(main, "api_call_log", [SimpleNamespace(model="m")])

    main.apply_result(state, result)

    assert state.history is history
    assert state.input_tokens == 5
    assert state.output_tokens == 7
    assert len(state.last_api_calls) == 1
    assert printed == [new_msgs]


def test_read_user_input_eof_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(main, "print_divider", lambda: None)

    class Boom:
        def prompt(self, *_args, **_kwargs):
            raise EOFError

    monkeypatch.setattr(main, "prompt_session", Boom())
    assert main.read_user_input() is None


def test_read_user_input_strips(monkeypatch) -> None:
    monkeypatch.setattr(main, "print_divider", lambda: None)
    session = MagicMock()
    session.prompt.return_value = "  hello  "
    monkeypatch.setattr(main, "prompt_session", session)
    assert main.read_user_input() == "hello"
