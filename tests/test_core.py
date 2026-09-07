"""core.agent.core：Base URL 规范化。"""

from core.agent.core import MODEL_NAME, _normalize_openai_base_url


def test_model_name_from_env() -> None:
    # conftest 里 setdefault MODEL_NAME=test-model；若环境已有值则尊重原值
    assert isinstance(MODEL_NAME, str)
    assert MODEL_NAME


def test_normalize_strips_chat_completions() -> None:
    assert (
        _normalize_openai_base_url("https://api.example.com/v1/chat/completions")
        == "https://api.example.com/v1"
    )


def test_normalize_strips_completions() -> None:
    assert (
        _normalize_openai_base_url("https://api.example.com/v1/completions")
        == "https://api.example.com/v1"
    )


def test_normalize_keeps_plain_base() -> None:
    assert _normalize_openai_base_url("https://api.example.com/v1") == "https://api.example.com/v1"


def test_normalize_root_path_after_strip() -> None:
    # path 只剩 /chat/completions 时，应回落到 /
    assert (
        _normalize_openai_base_url("https://api.example.com/chat/completions")
        == "https://api.example.com/"
    )
