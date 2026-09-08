"""core.cli：命令分发与结果写回 SessionState。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from core import cli
from core.ui.commands import SessionState


def test_handle_command_pass_for_normal_input() -> None:
    state = SessionState()
    assert cli.handle_command("写个 hello world", state) == "pass"


def test_handle_command_unknown(capsys) -> None:
    state = SessionState()
    assert cli.handle_command("/nope", state) == "continue"
    assert "未知命令" in capsys.readouterr().out


def test_handle_command_help_continues() -> None:
    state = SessionState()
    assert cli.handle_command("/help", state) == "continue"


def test_handle_command_exit_breaks() -> None:
    state = SessionState()
    assert cli.handle_command("/exit", state) == "break"


def test_apply_result_updates_state(monkeypatch) -> None:
    state = SessionState()
    history = [SimpleNamespace(parts=[])]
    result = SimpleNamespace(
        all_messages=lambda: history,
        usage=SimpleNamespace(input_tokens=5, output_tokens=7),
    )

    monkeypatch.setattr(cli, "api_call_log", [SimpleNamespace(model="m")])

    cli.apply_result(state, result)

    assert state.history is history
    assert state.input_tokens == 5
    assert state.output_tokens == 7
    assert len(state.last_api_calls) == 1


def test_read_user_input_eof_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(cli, "print_divider", lambda: None)

    class Boom:
        def prompt(self, *_args, **_kwargs):
            raise EOFError

    monkeypatch.setattr(cli, "prompt_session", Boom())
    assert cli.read_user_input() is None


def test_read_user_input_strips(monkeypatch) -> None:
    monkeypatch.setattr(cli, "print_divider", lambda: None)
    session = MagicMock()
    session.prompt.return_value = "  hello  "
    monkeypatch.setattr(cli, "prompt_session", session)
    assert cli.read_user_input() == "hello"
