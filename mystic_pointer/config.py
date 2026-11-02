"""Configuration manager for Mystic Pointer.

Handles persistence across Windows and Linux.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


def _get_default_config_path() -> Path:
    if os.name == "nt":
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
    else:
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) if xdg_config else Path.home() / ".config"
    config_dir = base / "mystic_pointer"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


@dataclass
class AppConfig:
    provider: str = "gemini"  # "gemini" | "openai" | "mock"
    gemini_api_key: str = ""
    # The "latest" alias is always offered to new API keys and avoids pinning a
    # concrete version that Google may retire for new accounts.
    gemini_model: str = "gemini-flash-latest"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    wiggle_enabled: bool = True
    wiggle_sensitivity: int = 5  # 1 (low) to 10 (high)
    hotkey: str = "Ctrl+Alt+G"
    smart_detection: bool = True
    dim_opacity: float = 0.45
    accent_color: str = "#3584e4"  # GNOME blue accent
    custom_suggestions: list[str] = field(
        default_factory=lambda: [
            "Summarize",
            "Explain",
            "Compare",
            "Extract text",
            "Translate to English",
            "What is this?",
        ]
    )

    @classmethod
    def load(cls, path: Path | None = None) -> AppConfig:
        config_file = path or _get_default_config_path()
        if not config_file.exists():
            cfg = cls()
            # Also check if GEMINI_API_KEY or OPENAI_API_KEY environment variables are present
            cfg.gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
            cfg.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
            return cfg

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Filter unknown keys to remain forward-compatible
            valid_keys = {k for k in cls.__dataclass_fields__}
            filtered = {k: v for k, v in data.items() if k in valid_keys}
            cfg = cls(**filtered)
            if not cfg.gemini_api_key:
                cfg.gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
            if not cfg.openai_api_key:
                cfg.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
            return cfg
        except Exception:
            return cls()

    def save(self, path: Path | None = None) -> None:
        config_file = path or _get_default_config_path()
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2)
        except Exception as e:
            print(f"[MysticPointer] Failed to save config: {e}")
