"""System tray icon and status-area integration for Mystic Pointer."""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from mystic_pointer.config import AppConfig
from mystic_pointer.core.screen_capture import is_wayland_session
from mystic_pointer.ui.icons import create_tray_icon_pixmap
from mystic_pointer.ui.style import (
    settings_palette,
    system_is_dark,
    tray_menu_stylesheet,
)

__all__ = ["MysticPointerTray", "create_tray_icon_pixmap"]


class MysticPointerTray(QObject):
    """Manages the status icon, quick toggles, and context menu."""

    activate_requested = Signal()
    settings_requested = Signal()
    shortcut_requested = Signal()
    quit_requested = Signal()
    state_changed = Signal(bool)

    def __init__(self, config: AppConfig, parent: QObject | None = None):
        super().__init__(parent)
        self.config = config
        self.is_enabled = True

        self.tray_icon = QSystemTrayIcon(parent)
        self._update_icon()
        self._build_menu()

        self.tray_icon.activated.connect(self._on_tray_activated)

    def show(self) -> None:
        self.tray_icon.show()

    def show_message(self, title: str, message: str, timeout_ms: int = 6000) -> None:
        """Show a desktop notification, falling back to the console."""
        print(f"[MysticPointer] {title}: {message}")
        if self.tray_icon.isVisible():
            self.tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                timeout_ms,
            )

    def _update_icon(self) -> None:
        self.tray_icon.setIcon(QIcon(create_tray_icon_pixmap(self.is_enabled)))
        state = "Enabled" if self.is_enabled else "Disabled"
        if is_wayland_session():
            hint = self.config.hotkey
        else:
            hint = f"{self.config.hotkey} or cursor wiggle"
        self.tray_icon.setToolTip(f"Mystic Pointer — {state} · {hint}")

    def _build_menu(self) -> None:
        dark = system_is_dark()
        menu = QMenu()
        menu.setStyleSheet(tray_menu_stylesheet(dark))
        menu.setPalette(settings_palette(dark))

        self.activate_action = QAction("Open Mystic Pointer", menu)
        self.activate_action.triggered.connect(self.activate_requested.emit)
        menu.addAction(self.activate_action)

        menu.addSeparator()

        self.turn_on_action = QAction("Enabled", menu)
        self.turn_on_action.setCheckable(True)
        self.turn_on_action.setChecked(self.is_enabled)
        self.turn_on_action.toggled.connect(self._on_toggle_turned_on)
        menu.addAction(self.turn_on_action)

        self.wiggle_action = QAction("Allow cursor wiggle", menu)
        self.wiggle_action.setCheckable(True)
        self.wiggle_action.setChecked(
            self.config.wiggle_enabled if not is_wayland_session() else False
        )
        self.wiggle_action.toggled.connect(self._on_toggle_wiggle)
        if is_wayland_session():
            self.wiggle_action.setEnabled(False)
            self.wiggle_action.setToolTip(
                "Cursor wiggle is unavailable on Wayland. Use the system shortcut."
            )
            menu.setToolTipsVisible(True)
        menu.addAction(self.wiggle_action)

        menu.addSeparator()

        settings_action = QAction("Preferences", menu)
        settings_action.triggered.connect(self.settings_requested.emit)
        menu.addAction(settings_action)

        if os.name != "nt":
            self.shortcut_action = QAction(f"Set Up {self.config.hotkey} Shortcut…", menu)
            self.shortcut_action.triggered.connect(self.shortcut_requested.emit)
            menu.addAction(self.shortcut_action)

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.is_enabled:
                self.activate_requested.emit()

    def _on_toggle_turned_on(self, enabled: bool) -> None:
        self.is_enabled = enabled
        self._update_icon()
        self.state_changed.emit(enabled)

    def _on_toggle_wiggle(self, enabled: bool) -> None:
        self.config.wiggle_enabled = enabled
        self.config.save()

    def update_from_config(self, config: AppConfig) -> None:
        self.config = config
        self.wiggle_action.setChecked(config.wiggle_enabled if not is_wayland_session() else False)
        shortcut_action = getattr(self, "shortcut_action", None)
        if shortcut_action is not None:
            shortcut_action.setText(f"Set Up {config.hotkey} Shortcut…")
        self._update_icon()
