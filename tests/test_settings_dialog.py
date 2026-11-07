"""Tests for preferences that affect the selection action bar."""

from __future__ import annotations

from typing import cast

from PySide6.QtWidgets import QApplication

from mystic_pointer.config import AppConfig
from mystic_pointer.ui.settings_dialog import SettingsDialog

_app = cast(QApplication, QApplication.instance() or QApplication([]))


def test_merge_copied_images_preference_round_trips(monkeypatch) -> None:
    monkeypatch.setattr(AppConfig, "save", lambda self, path=None: None)
    config = AppConfig(copy_merge_images=True)
    dialog = SettingsDialog(config)
    try:
        assert dialog.copy_merge_cb.isChecked()

        dialog.copy_merge_cb.setChecked(False)
        dialog._save_and_close()

        assert config.copy_merge_images is False
    finally:
        dialog.deleteLater()
