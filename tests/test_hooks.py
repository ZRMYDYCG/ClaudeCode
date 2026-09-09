"""core.agent.hooks：API 调用记录、请求重试、工具异常兜底。"""

import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior

from core.agent.hooks import (
    MAX_RETRIES,
    ApiCall,
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
