"""Base AI Provider interface for Mystic Pointer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generator

from PIL import Image


class AIProvider(ABC):
    """Abstract base class for multimodal AI providers."""

    @abstractmethod
    def generate_response(
        self,
        prompt: str,
        images: list[Image.Image],
    ) -> Generator[str, None, None]:
        """Stream response chunks from the model for the given prompt and image(s)."""
        pass

    @abstractmethod
    def validate_connection(self) -> tuple[bool, str]:
        """Validate API credentials and model accessibility."""
        pass
