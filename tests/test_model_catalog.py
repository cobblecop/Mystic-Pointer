"""Tests for provider model discovery and vision filtering."""

from mystic_pointer.ai.model_catalog import (
    DEFAULT_GEMINI_MODELS,
    ModelCatalog,
    gemini_model_is_legacy,
    is_vision_model_name,
    ollama_vision_capability,
    parse_gemini_models,
    parse_openai_models,
    sort_gemini_models,
)


def _gemini(name: str, methods: list[str], display: str = "") -> dict:
    return {
        "name": f"models/{name}",
        "displayName": display or name,
        "description": f"{display or name} description",
        "supportedGenerationMethods": methods,
    }


def test_gemini_catalog_keeps_multimodal_chat_models():
    payload = {
        "models": [
            _gemini("gemini-2.5-flash", ["generateContent", "countTokens"], "Gemini 2.5 Flash"),
            _gemini("gemini-3.8-flash", ["generateContent"]),
            _gemini("gemma-4-31b-it", ["generateContent"]),
            _gemini("gemini-omni-1.1-flash", ["generateContent"]),
            _gemini("gemini-2.5-flash-image", ["generateContent"]),
            _gemini("gemini-2.5-flash-preview-tts", ["generateContent"]),
            _gemini("gemini-3.5-transcribe", ["generateContent"]),
            _gemini("gemini-embedding-001", ["embedContent"]),
            _gemini("veo-3.1-generate-preview", ["predictLongRunning"]),
            _gemini("gemini-2.5-flash-native-audio-latest", ["bidiGenerateContent"]),
        ]
    }

    models = parse_gemini_models(payload)
    assert [m.id for m in models] == [
        "gemini-2.5-flash",
        "gemini-3.8-flash",
        "gemma-4-31b-it",
        "gemini-omni-1.1-flash",
    ]
    assert models[0].display_name == "Gemini 2.5 Flash"
    assert models[0].label == "Gemini 2.5 Flash"


def test_gemini_catalog_deduplicates_models():
    payload = {
        "models": [
            _gemini("gemini-2.5-flash", ["generateContent"]),
            _gemini("gemini-2.5-flash", ["generateContent"]),
        ]
    }
    assert len(parse_gemini_models(payload)) == 1


def test_gemini_models_sort_aliases_and_newest_first():
    payload = {
        "models": [
            _gemini("gemini-2.5-flash", ["generateContent"]),
            _gemini("gemini-3-flash-preview", ["generateContent"]),
            _gemini("gemini-3.8-flash", ["generateContent"]),
            _gemini("gemini-flash-latest", ["generateContent"]),
            _gemini("gemini-pro-latest", ["generateContent"]),
            _gemini("gemma-4-31b-it", ["generateContent"]),
            _gemini("gemini-3.1-pro-preview", ["generateContent"]),
            _gemini("gemini-flash-lite-latest", ["generateContent"]),
        ]
    }

    sorted_models = sort_gemini_models(parse_gemini_models(payload))
    assert [m.id for m in sorted_models] == [
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-pro-latest",
        "gemini-3.8-flash",
        "gemini-2.5-flash",
        "gemma-4-31b-it",
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
    ]


def test_default_and_legacy_gemini_models():
    assert DEFAULT_GEMINI_MODELS[0][0] == "gemini-flash-latest"
    assert gemini_model_is_legacy("gemini-2.5-flash")
    assert gemini_model_is_legacy("gemini-1.5-pro")
    assert not gemini_model_is_legacy("gemini-flash-latest")


def test_openai_host_filters_text_only_models():
    payload = {
        "data": [
            {"id": "gpt-4o"},
            {"id": "gpt-4o-mini"},
            {"id": "gpt-4.1"},
            {"id": "o1"},
            {"id": "o1-mini"},
            {"id": "o3-mini"},
            {"id": "gpt-3.5-turbo"},
            {"id": "gpt-4"},
            {"id": "gpt-4-0613"},
            {"id": "text-embedding-3-small"},
            {"id": "whisper-1"},
            {"id": "dall-e-3"},
            {"id": "gpt-4o-audio-preview"},
        ]
    }

    models = parse_openai_models(payload, openai_host=True)
    assert [m.id for m in models] == ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "o1"]


def test_generic_endpoint_keeps_unknown_local_models():
    payload = {
        "data": [
            {"id": "llama3.2-vision:latest"},
            {"id": "llava:13b"},
            {"id": "nomic-embed-text:latest"},
            {"id": "my-custom-vlm"},
            {"id": "qwen2.5-vl:7b"},
        ]
    }

    models = parse_openai_models(payload, openai_host=False)
    assert [m.id for m in models] == [
        "llama3.2-vision:latest",
        "llava:13b",
        "my-custom-vlm",
        "qwen2.5-vl:7b",
    ]


def test_vision_name_heuristics():
    assert is_vision_model_name("llava:13b")
    assert is_vision_model_name("qwen2.5-vl:7b")
    assert is_vision_model_name("gemma-4-31b-it")
    assert is_vision_model_name("gpt-4o", openai_host=True)
    assert not is_vision_model_name("nomic-embed-text")
    assert not is_vision_model_name("gpt-3.5-turbo", openai_host=True)
    assert not is_vision_model_name("o1-mini", openai_host=True)


def test_ollama_capabilities():
    assert ollama_vision_capability({"capabilities": ["completion", "vision"]}) is True
    assert ollama_vision_capability({"capabilities": ["completion"]}) is False
    assert ollama_vision_capability({"details": {}}) is None


def test_model_catalog_defaults():
    catalog = ModelCatalog()
    assert catalog.models == []
    assert catalog.error == ""
