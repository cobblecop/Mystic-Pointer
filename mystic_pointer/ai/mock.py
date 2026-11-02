"""Mock AI provider for offline testing and demo mode."""

from __future__ import annotations

import time
from collections.abc import Generator

from PIL import Image

from mystic_pointer.ai.base import AIProvider


class MockProvider(AIProvider):
    """Offline demo provider."""

    def generate_response(
        self,
        prompt: str,
        images: list[Image.Image],
    ) -> Generator[str, None, None]:
        num_images = len(images)
        intro = (
            "Demo response\n\n"
            f"Analyzed {num_images} selected screen region"
            f"{'s' if num_images > 1 else ''} for:\n"
            f'"{prompt}"\n\n'
        )

        if "compare" in prompt.lower() or num_images > 1:
            body = (
                "Comparison summary\n"
                "- Item 1: primary visual content selected.\n"
                "- Item 2: secondary element compared alongside Item 1.\n"
                "- Key differences: layout, visual contrast, and hierarchy.\n\n"
                "Connect an AI provider in Preferences for live responses."
            )
        elif "summarize" in prompt.lower():
            body = (
                "Summary\n"
                "- Main idea: the selection contains interface elements or text.\n"
                "- Context: screen content captured by Mystic Pointer.\n\n"
                "Connect an AI provider in Preferences for full multimodal analysis."
            )
        elif "extract" in prompt.lower():
            body = "Extracted text (preview)\n[Sample text from the selected region]\n"
        else:
            body = (
                "Here is what the demo provider found:\n\n"
                "1. The selection contains structured interface content.\n"
                "2. Add more regions with Ctrl+Click or the + Add button.\n\n"
                "Tip: configure an AI provider in Preferences to enable live analysis."
            )

        words = (intro + body).split(" ")
        for index, word in enumerate(words):
            suffix = " " if index < len(words) - 1 else ""
            yield word + suffix
            time.sleep(0.015)

    def validate_connection(self) -> tuple[bool, str]:
        return True, "Mock provider is always available"
