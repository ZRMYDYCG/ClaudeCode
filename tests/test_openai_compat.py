"""OpenAI 兼容响应清洗。"""

from openai.types import chat
from pydantic_ai.models import openai as openai_model
from pydantic_ai.providers.openai import OpenAIProvider

from core.agent.openai_compat import CompatibleOpenAIChatModel, _coerce_chat_completion_payload


def test_coerce_fixes_object_and_index() -> None:
    data = {
        "id": "x",
        "object": "completion",  # wrong
        "created": 1,
        "model": "m",
        "choices": [
            {
                "index": "0",  # string
                "message": {"role": "assistant", "content": "hi"},
                "finish_reason": None,
            }
        ],
    }
    fixed = _coerce_chat_completion_payload(data)
    assert fixed["object"] == "chat.completion"
    assert fixed["choices"][0]["index"] == 0
    assert fixed["choices"][0]["finish_reason"] == "stop"


def test_validate_completion_accepts_coerced_payload() -> None:
    payload = {
        "id": "x",
        "object": "wrong",
        "created": 1,
        "model": "m",
        "choices": [
            {
                "index": "0",
                "message": {"role": "assistant", "content": "hi"},
                "finish_reason": None,
            }
        ],
    }
    coerced = _coerce_chat_completion_payload(payload)
    # 未 coerce 时 _ChatCompletion 会因 object/index 失败；coerce 后应通过
    validated = openai_model._ChatCompletion.model_validate(coerced)
    assert validated.choices[0].index == 0
    assert validated.object == "chat.completion"

    model = CompatibleOpenAIChatModel(
        "m",
        provider=OpenAIProvider(api_key="test-key", base_url="https://example.com/v1"),
    )
    completion = chat.ChatCompletion.model_validate(coerced)
    again = model._validate_completion(completion)
    assert again.choices[0].index == 0
