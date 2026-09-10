"""core.agent.hooks：API 调用记录、请求重试、权限检查、工具异常兜底。"""

import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior

from core import permissions
from core.agent.hooks import (
    MAX_RETRIES,
    ApiCall,
    _check_permission,
    _handle_tool_error,
    _record_request,
    _record_response,
    _retry_on_error,
    api_call_log,
)


def test_api_call_defaults() -> None:
    call = ApiCall(model="m", messages_count=1, last_part=None, tools=["t"])
    assert call.finish_reason == ""
    assert call.parts_kinds == []
    assert call.input_tokens == 0
    assert call.output_tokens == 0


def test_record_request_and_response() -> None:
    api_call_log.clear()
    last_part = SimpleNamespace(part_kind="user-prompt", content="hi")
    msg = SimpleNamespace(parts=[last_part])
    request_context = SimpleNamespace(
        messages=[msg],
        model=SimpleNamespace(model_name="test-model"),
        model_request_parameters=SimpleNamespace(
            function_tools=[SimpleNamespace(name="read_file")]
        ),
    )

    returned = asyncio.run(_record_request(None, request_context))
    assert returned is request_context
    assert len(api_call_log) == 1
    assert api_call_log[0].model == "test-model"
    assert api_call_log[0].messages_count == 1
    assert api_call_log[0].last_part is last_part
    assert api_call_log[0].tools == ["read_file"]

    response = SimpleNamespace(
        finish_reason="stop",
        parts=[SimpleNamespace(part_kind="text")],
        usage=SimpleNamespace(input_tokens=11, output_tokens=22),
    )
    assert (
        asyncio.run(_record_response(None, request_context=request_context, response=response))
        is response
    )
    assert api_call_log[0].finish_reason == "stop"
    assert api_call_log[0].parts_kinds == ["text"]
    assert api_call_log[0].input_tokens == 11
    assert api_call_log[0].output_tokens == 22


def test_record_request_without_tools_attr() -> None:
    api_call_log.clear()
    request_context = SimpleNamespace(
        messages=[],
        model=SimpleNamespace(model_name="m"),
        model_request_parameters=SimpleNamespace(),  # 无 function_tools
    )
    asyncio.run(_record_request(None, request_context))
    assert api_call_log[0].tools == []
    assert api_call_log[0].last_part is None


def test_retry_on_http_5xx_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("core.agent.hooks.asyncio.sleep", fake_sleep)

    calls = {"n": 0}

    async def handler(_ctx: object) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ModelHTTPError(status_code=503, model_name="m")
        return "ok"

    result = asyncio.run(_retry_on_error(None, request_context=object(), handler=handler))
    assert result == "ok"
    assert calls["n"] == 2
    assert sleeps == [1]


def test_retry_on_http_4xx_does_not_retry() -> None:
    async def handler(_ctx: object) -> str:
        raise ModelHTTPError(status_code=400, model_name="m")

    with pytest.raises(ModelHTTPError):
        asyncio.run(_retry_on_error(None, request_context=object(), handler=handler))


def test_retry_on_api_error_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("core.agent.hooks.asyncio.sleep", fake_sleep)

    async def handler(_ctx: object) -> str:
        raise ModelAPIError(model_name="m", message="down")

    with pytest.raises(ModelAPIError):
        asyncio.run(_retry_on_error(None, request_context=object(), handler=handler))


def test_retry_on_unexpected_model_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("core.agent.hooks.asyncio.sleep", fake_sleep)
    calls = {"n": 0}

    async def handler(_ctx: object) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise UnexpectedModelBehavior("bad schema")
        return "ok"

    result = asyncio.run(_retry_on_error(None, request_context=object(), handler=handler))
    assert result == "ok"
    assert calls["n"] == 2
    assert sleeps == [1]

    async def fake_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("core.agent.hooks.asyncio.sleep", fake_sleep)
    calls = {"n": 0}

    async def handler(_ctx: object) -> str:
        calls["n"] += 1
        raise ModelHTTPError(status_code=500, model_name="m")

    with pytest.raises(ModelHTTPError):
        asyncio.run(_retry_on_error(None, request_context=object(), handler=handler))
    assert calls["n"] == MAX_RETRIES + 1


def test_check_permission_allow_runs_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(permissions, "compute_decision", lambda *_a, **_k: "allow")
    calls: list[dict] = []

    async def handler(args: dict) -> str:
        calls.append(args)
        return "done"

    result = asyncio.run(
        _check_permission(
            None,
            call=SimpleNamespace(tool_name="write_file"),
            tool_def=None,
            args={"path": "/tmp/x"},
            handler=handler,
        )
    )
    assert result == "done"
    assert calls == [{"path": "/tmp/x"}]


def test_check_permission_once_and_always(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(permissions, "compute_decision", lambda *_a, **_k: "ask")
    permissions.state.session_allowed.clear()

    async def handler(_args: dict) -> str:
        return "ran"

    async def once(_tool: str, _args: dict) -> str:
        return "once"

    monkeypatch.setattr(permissions, "prompt_approval", once)
    assert (
        asyncio.run(
            _check_permission(
                None,
                call=SimpleNamespace(tool_name="run_command"),
                tool_def=None,
                args={"command": "ls"},
                handler=handler,
            )
        )
        == "ran"
    )
    assert "run_command" not in permissions.state.session_allowed

    async def always(_tool: str, _args: dict) -> str:
        return "always"

    monkeypatch.setattr(permissions, "prompt_approval", always)
    assert (
        asyncio.run(
            _check_permission(
                None,
                call=SimpleNamespace(tool_name="run_command"),
                tool_def=None,
                args={"command": "ls"},
                handler=handler,
            )
        )
        == "ran"
    )
    assert "run_command" in permissions.state.session_allowed
    permissions.state.session_allowed.clear()


def test_check_permission_deny_skips_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(permissions, "compute_decision", lambda *_a, **_k: "ask")

    async def deny(_tool: str, _args: dict) -> str:
        return "deny"

    monkeypatch.setattr(permissions, "prompt_approval", deny)

    async def handler(_args: dict) -> str:
        raise AssertionError("handler should not run")

    result = asyncio.run(
        _check_permission(
            None,
            call=SimpleNamespace(tool_name="write_file"),
            tool_def=None,
            args={"path": "/tmp/x"},
            handler=handler,
        )
    )
    assert "拒绝" in result
    assert "write_file" in result


def test_handle_tool_error_returns_message() -> None:
    call = SimpleNamespace(tool_name="read_file")
    result = asyncio.run(
        _handle_tool_error(
            None,
            call=call,
            tool_def=None,
            args={},
            error=ValueError("bad path"),
        )
    )
    assert "ValueError" in result
    assert "bad path" in result
    assert "read_file" not in result or "工具执行出错" in result
