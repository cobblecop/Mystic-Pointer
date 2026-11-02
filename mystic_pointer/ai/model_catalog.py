"""Discovery of vision-capable models offered by the configured AI provider.

The Gemini API returns model metadata, but (as of the v1beta API) no explicit
"input modalities" field.  We therefore keep the general-purpose Gemini/Gemma
chat families and drop specialised models (embeddings, TTS, image generation,
live/audio, transcription, ...).  OpenAI-compatible endpoints only return model
IDs; Ollama additionally exposes per-model ``capabilities``, which we use when
available.  Everything here is blocking and must run off the GUI thread.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests

GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# Shown before an API key is available and used if discovery fails.  The
# "-latest" aliases are deliberately preferred: Google keeps them pointed at a
# model that new API keys can use.
DEFAULT_GEMINI_MODELS = (
    ("gemini-flash-latest", "Gemini Flash Latest"),
    ("gemini-flash-lite-latest", "Gemini Flash-Lite Latest"),
    ("gemini-pro-latest", "Gemini Pro Latest"),
)

# Older defaults that Google may no longer offer to newly created API keys.
# They are kept selectable, but the settings dialog points out the risk.
LEGACY_GEMINI_MODELS = frozenset(
    {
        "gemini-2.5-flash",
        "gemini-2.0-flash-exp",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    }
)

_GEMINI_ALIAS_PRIORITY = {
    "gemini-flash-latest": 0,
    "gemini-flash-lite-latest": 1,
    "gemini-pro-latest": 2,
}

_GEMINI_NON_VISION_TOKENS = (
    "embedding",
    "embed",
    "-tts",
    "tts",
    "transcribe",
    "-image",
    "image-",
    "nano-banana",
    "imagen",
    "lyria",
    "veo",
    "aqa",
    "robotics",
    "computer-use",
    "deep-research",
    "antigravity",
    "-live",
    "native-audio",
    "audio",
)

# Names that are certainly not image-capable chat models.
_NON_VISION_TOKENS = (
    "embedding",
    "embed-",
    "embed_",
    "text-embedding",
    "bge-",
    "e5-",
    "whisper",
    "transcrib",
    "text-to-speech",
    "tts",
    "dall-e",
    "moderation",
    "rerank",
    "stable-diffusion",
    "sdxl",
    "flux",
    "audio",
    "realtime",
    "computer-use",
    "gpt-3.5",
)

# Families that are known to accept images.  Deliberately permissive: unknown
# models on third-party endpoints are kept (a local server usually exposes only
# the models it can run, and there is no standard capability API).
_VISION_TOKENS = (
    "vision",
    "multimodal",
    "llava",
    "bakllava",
    "minicpm-v",
    "moondream",
    "pixtral",
    "internvl",
    "cogvlm",
    "idefics",
    "paligemma",
    "smolvlm",
    "florence",
    "fuyu",
    "kosmos",
    "nvila",
    "glm-4v",
    "glm-4.1v",
    "yi-vl",
    "deepseek-vl",
    "step-1v",
    "ovis",
    "qwen-vl",
    "qwen2-vl",
    "qwen2.5-vl",
    "qwen3-vl",
    "-vl",
    "vl-",
    "llama3.2-vision",
    "llama-3.2-vision",
    "llama4",
    "llama-4",
    "gemma3",
    "gemma-3",
    "gemma4",
    "gemma-4",
    "phi-4-multimodal",
    "phi4-multimodal",
    "granite-vision",
    "granite3.2-vision",
)

_OPENAI_VISION_PREFIXES = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-4.5",
    "gpt-5",
    "chatgpt",
    "o1",
    "o3",
    "o4",
    "gpt-4-turbo",
    "gpt-4-vision",
)

_OPENAI_TEXT_ONLY_PREFIXES = (
    "o1-mini",
    "o1-preview",
    "o3-mini",
    "gpt-4-0",  # gpt-4-0314 / gpt-4-0613
    "gpt-4-32k",
)


@dataclass(frozen=True)
class ModelInfo:
    """A model that can be selected for screen analysis."""

    id: str
    display_name: str = ""
    description: str = ""

    @property
    def label(self) -> str:
        if self.display_name and self.display_name != self.id:
            return self.display_name
        return self.id


@dataclass
class ModelCatalog:
    """Result of a model discovery request."""

    models: list[ModelInfo] = field(default_factory=list)
    error: str = ""


def _sanitize(message: str, secrets: tuple[str, ...] = ()) -> str:
    text = str(message)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    text = " ".join(text.split())
    return text[:300]


def _response_error(response: requests.Response, provider: str) -> str:
    detail = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                detail = str(error.get("message", ""))
            elif error:
                detail = str(error)
    except ValueError:
        pass
    if not detail:
        detail = response.reason or "request failed"
    return f"{provider} returned HTTP {response.status_code}: {detail}"


def gemini_model_is_vision_capable(metadata: dict) -> bool:
    """Return True for general-purpose Gemini/Gemma chat models."""
    raw_name = metadata.get("name")
    if not isinstance(raw_name, str) or not raw_name:
        return False
    methods = metadata.get("supportedGenerationMethods")
    if not isinstance(methods, list) or "generateContent" not in methods:
        return False

    model_id = raw_name.removeprefix("models/").lower()
    if not (model_id.startswith("gemini") or model_id.startswith("gemma")):
        return False
    return not any(token in model_id for token in _GEMINI_NON_VISION_TOKENS)


def parse_gemini_models(payload: dict) -> list[ModelInfo]:
    """Extract multimodal models from a ``models.list`` response."""
    raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        return []

    found: dict[str, ModelInfo] = {}
    for metadata in raw_models:
        if not isinstance(metadata, dict) or not gemini_model_is_vision_capable(metadata):
            continue
        raw_name = str(metadata.get("name", ""))
        model_id = raw_name.removeprefix("models/")
        if not model_id:
            continue
        display_name = str(metadata.get("displayName") or model_id)
        description = str(metadata.get("description") or "")
        found.setdefault(
            model_id,
            ModelInfo(id=model_id, display_name=display_name, description=description),
        )
    return list(found.values())


def _gemini_version(model_id: str) -> float:
    match = re.search(r"(?:gemini|gemma)-(\d+(?:\.\d+)?)", model_id)
    return float(match.group(1)) if match else 0.0


def _gemini_sort_key(model: ModelInfo) -> tuple[int, int, float, str]:
    model_id = model.id.lower()
    alias_rank = _GEMINI_ALIAS_PRIORITY.get(model_id)
    if alias_rank is not None:
        return (0, alias_rank, 0.0, model_id)

    is_preview = any(token in model_id for token in ("preview", "experimental", "customtools"))
    family_rank = 0 if model_id.startswith("gemini") else 1
    return (2 if is_preview else 1, family_rank, -_gemini_version(model_id), model_id)


def sort_gemini_models(models: list[ModelInfo]) -> list[ModelInfo]:
    """Put stable aliases and newer models before previews and old versions."""
    return sorted(models, key=_gemini_sort_key)


def gemini_model_is_legacy(model_id: str) -> bool:
    """Return True for old defaults that new API keys may not be able to use."""
    return model_id.strip() in LEGACY_GEMINI_MODELS


def fetch_gemini_models(api_key: str, timeout: float = 12.0) -> ModelCatalog:
    """List multimodal models available to this Gemini API key."""
    api_key = api_key.strip()
    if not api_key:
        return ModelCatalog(error="Enter a Gemini API key to load models.")

    models: list[ModelInfo] = []
    page_token: str | None = None
    try:
        for _ in range(10):  # Defensive cap; a page holds up to 1000 models.
            params: dict[str, str | int] = {"key": api_key, "pageSize": 1000}
            if page_token:
                params["pageToken"] = page_token
            response = requests.get(GEMINI_MODELS_URL, params=params, timeout=timeout)
            if response.status_code != 200:
                error = _response_error(response, "Gemini")
                return ModelCatalog(error=_sanitize(error, (api_key,)))

            payload = response.json()
            if not isinstance(payload, dict):
                return ModelCatalog(error="Gemini returned an unexpected response.")
            models.extend(parse_gemini_models(payload))

            next_token = payload.get("nextPageToken")
            if not isinstance(next_token, str) or not next_token:
                break
            page_token = next_token
    except Exception as exc:  # noqa: BLE001 - surfaced in the settings dialog
        return ModelCatalog(error=_sanitize(str(exc), (api_key,)))

    # De-duplicate while preserving API order, then surface the aliases and
    # newer stable models first.
    unique: dict[str, ModelInfo] = {}
    for model in models:
        unique.setdefault(model.id, model)
    return ModelCatalog(models=sort_gemini_models(list(unique.values())))


def is_vision_model_name(model_id: str, *, openai_host: bool = False) -> bool:
    """Best-effort vision check for endpoints without capability metadata."""
    name = model_id.strip().lower()
    if not name:
        return False
    if any(token in name for token in _NON_VISION_TOKENS):
        return False
    if name.startswith(_OPENAI_TEXT_ONLY_PREFIXES):
        return False
    if any(token in name for token in _VISION_TOKENS):
        return True
    if name.startswith(_OPENAI_VISION_PREFIXES):
        return True
    # Unknown model on a third-party endpoint: keep it rather than hiding a
    # custom vision model that the provider cannot describe.
    return not openai_host


def parse_openai_models(payload: dict, *, openai_host: bool = False) -> list[ModelInfo]:
    """Extract vision models from an OpenAI-compatible ``/models`` response."""
    raw_models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        return []

    found: dict[str, ModelInfo] = {}
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id") or item.get("name")
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        model_id = model_id.strip()
        if not is_vision_model_name(model_id, openai_host=openai_host):
            continue
        found.setdefault(model_id, ModelInfo(id=model_id))
    return list(found.values())


def _is_openai_host(base_url: str) -> bool:
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except ValueError:
        return False
    return host == "api.openai.com" or host.endswith(".openai.azure.com")


def _ollama_root(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")].rstrip("/")
    return root


def _is_ollama(root: str, timeout: float, headers: dict[str, str] | None = None) -> bool:
    try:
        response = requests.get(
            f"{root}/api/version",
            headers=headers or {},
            timeout=min(timeout, 2.0),
        )
        if response.status_code != 200:
            return False
        payload = response.json()
        return isinstance(payload, dict) and bool(payload.get("version"))
    except Exception:
        return False


def ollama_vision_capability(payload: dict) -> bool | None:
    """Read Ollama's ``capabilities`` list; None when the field is absent."""
    capabilities = payload.get("capabilities")
    if isinstance(capabilities, list):
        return "vision" in capabilities
    return None


def _ollama_show_capability(
    root: str,
    model_id: str,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> bool | None:
    try:
        response = requests.post(
            f"{root}/api/show",
            json={"model": model_id},
            headers=headers or {},
            timeout=min(timeout, 4.0),
        )
        if response.status_code != 200:
            return None
        payload = response.json()
        if not isinstance(payload, dict):
            return None
        return ollama_vision_capability(payload)
    except Exception:
        return None


def _ollama_models(
    root: str,
    model_ids: list[str],
    timeout: float,
    headers: dict[str, str] | None = None,
) -> list[ModelInfo]:
    capabilities: dict[str, bool | None] = {}
    workers = min(8, max(1, len(model_ids)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_ollama_show_capability, root, model_id, timeout, headers): model_id
            for model_id in model_ids
        }
        for future in as_completed(futures):
            model_id = futures[future]
            try:
                capabilities[model_id] = future.result()
            except Exception:
                capabilities[model_id] = None

    models: list[ModelInfo] = []
    for model_id in model_ids:
        capability = capabilities.get(model_id)
        if capability is True or (
            capability is None and is_vision_model_name(model_id, openai_host=False)
        ):
            models.append(ModelInfo(id=model_id))
    return models


def fetch_openai_models(
    base_url: str,
    api_key: str = "",
    timeout: float = 12.0,
) -> ModelCatalog:
    """List vision models from an OpenAI-compatible endpoint or Ollama."""
    base_url = base_url.strip()
    if not base_url:
        return ModelCatalog(error="Enter a base URL to load models.")

    models_url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key.strip()}"} if api_key.strip() else {}
    try:
        response = requests.get(models_url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            error = _response_error(response, "The endpoint")
            return ModelCatalog(error=_sanitize(error, (api_key,)))
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - surfaced in the settings dialog
        return ModelCatalog(error=_sanitize(str(exc), (api_key,)))

    raw_models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        return ModelCatalog(error="The endpoint returned an unexpected response.")

    model_ids: list[str] = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id") or item.get("name")
        if isinstance(model_id, str) and model_id.strip():
            model_ids.append(model_id.strip())

    if not model_ids:
        return ModelCatalog()

    openai_host = _is_openai_host(base_url)
    if not openai_host:
        root = _ollama_root(base_url)
        if _is_ollama(root, timeout, headers):
            return ModelCatalog(models=_ollama_models(root, model_ids, timeout, headers))

    return ModelCatalog(models=parse_openai_models(payload, openai_host=openai_host))
