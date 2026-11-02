"""AI provider factory for Mystic Pointer.

Provider implementations are imported lazily: importing ``google-genai`` costs
seconds and would otherwise delay every application start, even for users who
only use the offline demo mode.
"""

from __future__ import annotations

from mystic_pointer.ai.base import AIProvider
from mystic_pointer.config import AppConfig


def get_provider(config: AppConfig) -> AIProvider:
    """Return the configured AI provider, falling back gracefully if unconfigured."""
    if config.provider == "gemini":
        if config.gemini_api_key:
            from mystic_pointer.ai.gemini import GeminiProvider

            return GeminiProvider(api_key=config.gemini_api_key, model=config.gemini_model)
        # If no key, return mock with a friendly warning message
        from mystic_pointer.ai.mock import MockProvider

        return MockProvider()
    elif config.provider == "openai":
        from mystic_pointer.ai.openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(
            base_url=config.openai_base_url,
            api_key=config.openai_api_key,
            model=config.openai_model,
        )
    from mystic_pointer.ai.mock import MockProvider

    return MockProvider()
