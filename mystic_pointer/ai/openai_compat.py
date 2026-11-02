"""OpenAI-compatible and Ollama vision provider."""

from __future__ import annotations

import base64
import io
import json
from typing import Generator

import requests
from PIL import Image

from mystic_pointer.ai.base import AIProvider


class OpenAICompatProvider(AIProvider):
    """Provider for OpenAI-compatible vision APIs (OpenAI, Ollama, OpenRouter, etc.)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "",
        model: str = "llama3.2-vision",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model.strip() or "llama3.2-vision"

    def _encode_image(self, img: Image.Image) -> str:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def generate_response(
        self,
        prompt: str,
        images: list[Image.Image],
    ) -> Generator[str, None, None]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        content_parts: list[dict] = []
        for img in images:
            b64_str = self._encode_image(img)
            content_parts.append(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_str}"}}
            )
        content_parts.append(
            {
                "type": "text",
                "text": prompt,
            }
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": content_parts,
                }
            ],
            "stream": True,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, stream=True, timeout=60)
            if resp.status_code != 200:
                yield f"Error ({resp.status_code}): {resp.text}"
                return

            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = (
                    raw_line
                    if isinstance(raw_line, str)
                    else raw_line.decode("utf-8", errors="ignore")
                )
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            text = delta.get("content", "")
                            if text:
                                yield text
                    except Exception:
                        pass
        except Exception as e:
            yield f"Connection error to {self.base_url}: {e}"

    def validate_connection(self) -> tuple[bool, str]:
        url = f"{self.base_url}/models"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                return True, "Connected successfully"
            return False, f"HTTP {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, str(e)
