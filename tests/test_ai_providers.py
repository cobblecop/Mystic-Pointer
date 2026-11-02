"""Tests for AI providers."""

from typing import Any, cast

from PIL import Image

from mystic_pointer.ai import get_provider
from mystic_pointer.ai.gemini import GeminiProvider
from mystic_pointer.ai.mock import MockProvider
from mystic_pointer.config import AppConfig


def test_mock_provider_streaming():
    provider = MockProvider()
    ok, msg = provider.validate_connection()
    assert ok
    assert "Mock" in msg

    img = Image.new("RGB", (100, 100), color="blue")
    chunks = list(provider.generate_response("Compare these items", [img, img]))
    full_text = "".join(chunks)
    assert len(chunks) > 0
    assert "Comparison" in full_text or "Analyzed" in full_text


def test_gemini_provider_unconfigured():
    provider = GeminiProvider(api_key="")
    chunks = list(provider.generate_response("Summarize", []))
    assert len(chunks) == 1
    assert "not configured" in chunks[0]


def test_retired_gemini_model_error_is_actionable():
    detail = (
        "This model models/gemini-2.5-flash is no longer available to new users. "
        "Please update your code to use models/gemini-3.8."
    )

    class FakeResponse:
        status_code = 404
        text = f'{{"error": {{"message": "{detail}"}}}}'

        def json(self) -> dict:
            return {"error": {"message": detail}}

    message = GeminiProvider._format_api_error(cast(Any, FakeResponse()))
    assert "no longer available" in message
    assert "Preferences → AI Providers" in message
    assert "Gemini Flash Latest" in message


def test_gemini_validation_checks_model_availability(monkeypatch):
    detail = "This model is no longer available to new users."

    class FakeResponse:
        status_code = 404
        text = detail

        def json(self) -> dict:
            return {"error": {"message": detail}}

    calls: list[str] = []

    def fake_post(url: str, **kwargs: Any) -> Any:
        calls.append(url)
        return FakeResponse()

    monkeypatch.setattr("mystic_pointer.ai.gemini.requests.post", fake_post)
    provider = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")

    ok, message = provider.validate_connection()

    assert not ok
    assert "no longer available" in message
    assert calls and ":countTokens" in calls[0]


def test_provider_factory():
    cfg_mock = AppConfig(provider="mock")
    assert isinstance(get_provider(cfg_mock), MockProvider)

    cfg_gemini = AppConfig(provider="gemini", gemini_api_key="test-key")
    assert isinstance(get_provider(cfg_gemini), GeminiProvider)
