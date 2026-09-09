"""
对 OpenAI 兼容网关做响应清洗：部分服务商偶发返回不规范字段，
导致 pydantic-ai 校验 ChatCompletion 失败（表现为「好一次、坏一次」）。
"""

from __future__ import annotations

from typing import Any

from openai.types import chat
from pydantic_ai.models import openai as openai_model
from pydantic_ai.models.openai import OpenAIChatModel


def _coerce_chat_completion_payload(data: dict[str, Any]) -> dict[str, Any]:
    """
    尽量把兼容网关的松散 JSON 修成 OpenAI ChatCompletion 能过校验的形状。
    """
    if data.get("object") != "chat.completion":
        data["object"] = "chat.completion"

    choices = data.get("choices")
    if isinstance(choices, list):
        for i, choice in enumerate(choices):
            if not isinstance(choice, dict):
                continue
            index = choice.get("index", i)
            if isinstance(index, str) and index.isdigit():
                choice["index"] = int(index)
            elif not isinstance(index, int):
                choice["index"] = i
            if choice.get("finish_reason") is None:
                choice["finish_reason"] = "stop"
    return data


class CompatibleOpenAIChatModel(OpenAIChatModel):
    """
    覆盖校验钩子：先 coerce，再走与父类相同的 _ChatCompletion 校验。
    """

    def _validate_completion(self, response: chat.ChatCompletion) -> Any:
        data = _coerce_chat_completion_payload(response.model_dump())
        return openai_model._ChatCompletion.model_validate(data)
