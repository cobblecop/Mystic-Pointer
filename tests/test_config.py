"""Tests for configuration persistence."""

from mystic_pointer.config import AppConfig


def test_config_defaults():
    cfg = AppConfig()
    assert cfg.provider == "gemini"
    assert cfg.gemini_model == "gemini-flash-latest"
    assert cfg.wiggle_enabled is True
    assert cfg.wiggle_sensitivity == 5
    assert cfg.hotkey == "Ctrl+Alt+G"
    assert cfg.copy_merge_images is False


def test_config_save_and_load(tmp_path):
    path = tmp_path / "test_config.json"
    cfg = AppConfig(
        provider="openai",
        wiggle_sensitivity=8,
        hotkey="Super+G",
        gemini_api_key="secret-key",
        copy_merge_images=True,
    )
    cfg.save(path)

    loaded = AppConfig.load(path)
    assert loaded.provider == "openai"
    assert loaded.wiggle_sensitivity == 8
    assert loaded.hotkey == "Super+G"
    assert loaded.gemini_api_key == "secret-key"
    assert loaded.copy_merge_images is True
