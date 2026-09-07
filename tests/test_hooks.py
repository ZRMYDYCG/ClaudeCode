"""core.agent.hooks：API 调用元数据记录。"""

import asyncio
from types import SimpleNamespace

from core.agent.hooks import ApiCall, _record_request, _record_response, api_call_log


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
    assert asyncio.run(_record_response(None, request_context, response)) is response
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
