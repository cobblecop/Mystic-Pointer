"""Google Gemini AI Provider for Mystic Pointer.

Supports multimodal analysis, comparisons, and streaming responses.  The model
is selected from the models discovered in the settings dialog.
"""

from __future__ import annotations

import base64
import io
from typing import Generator

import requests
from PIL import Image

from mystic_pointer.ai.base import AIProvider

try:
    from google import genai

    _HAS_GENAI_SDK = True
except ImportError:
    _HAS_GENAI_SDK = False


class GeminiProvider(AIProvider):
    """Google Gemini Multimodal Provider."""

    def __init__(self, api_key: str, model: str = "gemini-flash-latest"):
        self.api_key = api_key.strip()
        self.model = model.strip() or "gemini-flash-latest"
        self._client = None
        if _HAS_GENAI_SDK and self.api_key:
            try:
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"[GeminiProvider] SDK client init warning: {e}")

    @staticmethod
    def _format_api_error(response: requests.Response) -> str:
        """Turn a Google error response into a short, actionable message."""
        detail = response.text
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                detail = str(error.get("message") or detail)
            elif isinstance(error, str):
                detail = error

        message = f"Gemini API Error ({response.status_code}): {detail.strip()}"
        if response.status_code == 404:
            message += (
                "\n\nOpen Preferences → AI Providers and choose a currently "
                "available model (for example Gemini Flash Latest)."
            )
        return message

    def _prepare_contents(self, prompt: str, images: list[Image.Image]) -> list[object]:
        contents: list[object] = []
        for idx, img in enumerate(images):
            # Ensure RGB format
            rgb_img = img.convert("RGB")
            contents.append(rgb_img)
            if len(images) > 1:
                contents.append(f"[Image {idx + 1}]")
        contents.append(prompt)
        return contents

    def generate_response(
        self,
        prompt: str,
        images: list[Image.Image],
    ) -> Generator[str, None, None]:
        if not self.api_key:
            yield "Error: Gemini API Key is not configured. Please open Preferences to enter your API key."
            return

        # Attempt with SDK first if initialized
        if self._client is not None:
            try:
                contents: list[object] = self._prepare_contents(prompt, images)
                response = self._client.models.generate_content_stream(
                    model=self.model,
                    contents=contents,  # type: ignore
                )
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
                return
            except Exception as e:
                print(f"[GeminiProvider] SDK stream error, attempting REST fallback: {e}")

        # REST API fallback (v1beta)
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:streamGenerateContent?key={self.api_key}&alt=sse"
            parts: list[dict[str, object]] = []
            for img in images:
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=90)
                b64_data = base64.b64encode(buf.getvalue()).decode("utf-8")
                parts.append(
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": b64_data,
                        }
                    }
                )
            parts.append({"text": prompt})

            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {"temperature": 0.4},
            }

            resp = requests.post(url, json=payload, stream=True, timeout=30)
            if resp.status_code != 200:
                yield self._format_api_error(resp)
                return

            import json

            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = (
                    raw_line
                    if isinstance(raw_line, str)
                    else raw_line.decode("utf-8", errors="ignore")
                )
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if not data_str:
                    continue
                try:
                    data = json.loads(data_str)
                    candidates = data.get("candidates", [])
                    if candidates:
                        content = candidates[0].get("content", {})
                        for part in content.get("parts", []):
                            text = part.get("text", "")
                            if text:
                                yield text
                except Exception:
                    pass
        except Exception as e:
            yield f"Error communicating with Gemini: {str(e)}"

    def validate_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "API key is empty"
        try:
            # countTokens checks that this API key can actually use the model
            # (retired models return 404 here) without spending generation
            # quota or waiting for a full response.
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:countTokens?key={self.api_key}"
            )
            resp = requests.post(
                url,
                json={"contents": [{"parts": [{"text": "ping"}]}]},
                timeout=10,
            )
            if resp.status_code == 200:
                return True, "Connected successfully to Gemini"
            return False, self._format_api_error(resp)
        except Exception as e:
            return False, str(e)
