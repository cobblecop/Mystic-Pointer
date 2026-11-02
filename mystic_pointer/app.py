"""Main application coordinator and entry point for Mystic Pointer."""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QCursor, QGuiApplication, QScreen
from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QSystemTrayIcon,
)

from mystic_pointer.ai import get_provider
from mystic_pointer.ai.base import AIProvider
from mystic_pointer.config import AppConfig
from mystic_pointer.core.capture_service import CaptureService
from mystic_pointer.core.hotkey import GlobalHotkeyListener
from mystic_pointer.core.screen_capture import is_gnome_session, is_wayland_session
from mystic_pointer.core.wiggle_detector import WiggleDetector, WiggleThread
from mystic_pointer.ipc import ActivationServer
from mystic_pointer.ui.overlay import MysticPointerOverlay
from mystic_pointer.ui.settings_dialog import SettingsDialog
from mystic_pointer.ui.tray import MysticPointerTray


class MysticPointerApp(QObject):
    """Coordinates overlay, tray, gesture listener, and AI provider."""

    def __init__(self, qapp: QApplication, activation_only: bool = False):
        super().__init__()
        self.qapp = qapp
        self.config = AppConfig.load()
        self.provider: AIProvider = get_provider(self.config)

        # Fallback state for desktops without a system tray.
        self.solo_mode = False
        self.activation_only = activation_only
        self._quitting = False

        # Active overlay instance
        self.active_overlay: MysticPointerOverlay | None = None
        self.settings_dialog: SettingsDialog | None = None

        # Background capture (Wayland portal calls can take a few hundred ms)
        self.capture_service = CaptureService(self)

        # Single-instance activation, used by system shortcuts on Wayland
        self.activation_server = ActivationServer(self)
        self.activation_server.activated.connect(self.activate_mystic_pointer)

        # Wiggle gesture detector.  Wayland does not expose the global cursor
        # position to applications, so the gesture is only usable on X11.
        self.wiggle_supported = not is_wayland_session()
        self.wiggle_detector = WiggleDetector(
            sensitivity=self.config.wiggle_sensitivity,
            enabled=self.config.wiggle_enabled and self.wiggle_supported,
        )
        self.wiggle_thread = WiggleThread(self.wiggle_detector, self)
        self.wiggle_thread.wiggle_detected.connect(self._on_wiggle_detected)

        # Global Hotkey listener
        self.hotkey_listener = GlobalHotkeyListener(self.config.hotkey, self)
        self.hotkey_listener.activated.connect(self.activate_mystic_pointer)

        # System tray
        self.tray = MysticPointerTray(self.config)
        self.tray.activate_requested.connect(self.activate_mystic_pointer)
        self.tray.settings_requested.connect(self.open_settings)
        self.tray.shortcut_requested.connect(self.install_shortcut)
        self.tray.quit_requested.connect(self.quit)
        self.tray.state_changed.connect(self._on_state_changed)

    def start(self) -> None:
        """Start background listeners and display tray."""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        else:
            self._start_without_tray()
        if self.wiggle_supported:
            self.wiggle_thread.start()
        self.hotkey_listener.start()
        if not self.activation_only:
            # The long-running tray process keeps the system shortcut healthy.
            # A one-shot ``--activate`` launch skips this so the overlay is not
            # delayed by extra gsettings calls.
            self._repair_system_shortcut()

        # The first layout of the floating panel costs several hundred ms
        # (stylesheet + font metrics).  Pay it once at startup so the first
        # activation is snappy.
        QTimer.singleShot(0, self._warm_up_ui)

        if not self.wiggle_supported:
            hint = (
                "Bind a system shortcut to 'mystic-pointer --activate'."
                if self.solo_mode
                else "Activate from the tray or bind a system shortcut to "
                "'mystic-pointer --activate'."
            )
            print(
                "[MysticPointer] Wayland session detected: the wiggle gesture and "
                f"in-process global hotkey are unavailable. {hint}"
            )

    def _repair_system_shortcut(self) -> None:
        """Fix a registered GNOME shortcut whose command or binding is empty.

        GNOME only delivers a system shortcut when both fields are set.  An
        entry left half-configured (or created by hand) looks present but does
        nothing, so repair it silently at startup instead of asking again.
        """
        if not is_gnome_session():
            return
        from mystic_pointer.shortcut import repair_gnome_shortcut

        changed, message = repair_gnome_shortcut(self.config.hotkey)
        if changed:
            print(f"[MysticPointer] {message}")

    def _start_without_tray(self) -> None:
        """Degrade gracefully when no status-notifier/tray host is available.

        Without a tray there is no icon to click, so either show the settings
        dialog (normal start) or act as a one-shot activator (``--activate``).
        ``mystic-pointer --activate`` still works as a system shortcut target.
        """
        self.solo_mode = True
        print(
            "[MysticPointer] No system tray is available on this desktop. "
            "Running without a tray icon; bind a system shortcut to "
            "'mystic-pointer --activate' to trigger Mystic Pointer."
        )
        if not self.activation_only:
            QTimer.singleShot(0, self.open_settings)

    def _warm_up_ui(self) -> None:
        """Pre-build a throwaway panel to warm Qt's style and layout caches."""
        if self.active_overlay is not None:
            return
        try:
            # Load the PNG decoder and the GNOME D-Bus client now rather than
            # paying ~100 ms of first-use imports during the first activation.
            from PIL import Image

            Image.init()
            if is_gnome_session():
                import jeepney  # noqa: F401

            from mystic_pointer.ui.floating_panel import FloatingPanel
            from mystic_pointer.ui.selection import SelectionManager

            panel = FloatingPanel(SelectionManager(), self.provider, self.config)
            panel.ensurePolished()
            panel.sizeHint()
            panel.deleteLater()
        except Exception as exc:
            print(f"[MysticPointer] UI warm-up skipped: {exc}")

    def _screen_under_cursor(self) -> QScreen | None:
        screen = QGuiApplication.screenAt(QCursor.pos())
        return screen or QGuiApplication.primaryScreen()

    def activate_mystic_pointer(self) -> None:
        """Activate the Mystic Pointer screen overlay."""
        if self._quitting or not self.tray.is_enabled:
            return

        if self.active_overlay is not None:
            # Already active
            try:
                self.active_overlay.raise_()
                self.active_overlay.activateWindow()
            except RuntimeError:
                # The widget was destroyed without a close notification.
                self.active_overlay = None
            else:
                return

        screen = self._screen_under_cursor()
        if screen is None:
            self.tray.show_message("Mystic Pointer", "No screen was found.")
            return

        # Temporarily pause wiggle detection while overlay is active
        self.wiggle_detector.set_enabled(False)

        overlay = MysticPointerOverlay(
            self.config,
            self.provider,
            screen,
            self.capture_service,
        )
        self.active_overlay = overlay
        overlay.overlay_closed.connect(self._on_overlay_closed)
        overlay.capture_failed.connect(self._on_capture_failed)
        # Safety net for WA_DeleteOnClose: never keep a wrapper around after
        # Qt has deleted the underlying widget.
        overlay.destroyed.connect(lambda: self._forget_overlay(overlay))
        overlay.begin()

    def _forget_overlay(self, overlay: MysticPointerOverlay) -> None:
        if self.active_overlay is overlay:
            self.active_overlay = None

    def _on_capture_failed(self, message: str) -> None:
        self.tray.show_message("Mystic Pointer could not start", message)

    def _on_overlay_closed(self) -> None:
        self.active_overlay = None
        # Resume wiggle detection if supported and enabled in config
        self.wiggle_detector.set_enabled(self.config.wiggle_enabled and self.wiggle_supported)
        if self.solo_mode and self.activation_only:
            # One-shot invocation: nothing else is left to keep running.
            self.quit()

    def _on_wiggle_detected(self) -> None:
        if self.active_overlay is None and self.tray.is_enabled:
            self.activate_mystic_pointer()

    def _on_state_changed(self, enabled: bool) -> None:
        self.wiggle_detector.set_enabled(
            enabled and self.config.wiggle_enabled and self.wiggle_supported
        )

    def open_settings(self) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self.config)
            self.settings_dialog.settings_saved.connect(self._on_settings_saved)
            self.settings_dialog.finished.connect(self._on_settings_closed)
            self.settings_dialog.show()
        else:
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()

    def _on_settings_saved(self, new_config: AppConfig) -> None:
        self.config = new_config
        self.provider = get_provider(self.config)
        self.hotkey_listener.set_hotkey(self.config.hotkey)
        self.wiggle_detector.set_sensitivity(self.config.wiggle_sensitivity)
        self.wiggle_detector.set_enabled(self.config.wiggle_enabled and self.wiggle_supported)
        self.tray.update_from_config(self.config)

    def _on_settings_closed(self) -> None:
        self.settings_dialog = None
        if self.solo_mode:
            # There is no tray to return to, so don't linger invisibly.
            self.quit()

    def install_shortcut(self) -> None:
        """Offer to register a GNOME system shortcut (needed on Wayland)."""
        from mystic_pointer.shortcut import install_gnome_shortcut, is_gnome_desktop

        if not is_gnome_desktop():
            self.tray.show_message(
                "System shortcut",
                "This desktop does not allow automatic shortcut setup. "
                "Create a shortcut that runs: mystic-pointer --activate",
                9000,
            )
            return

        answer = QMessageBox.question(
            None,
            "Set up system shortcut",
            f"Add {self.config.hotkey} as a system-wide shortcut for Mystic Pointer?\n\n"
            "This adds a custom shortcut in GNOME Settings. You can remove it there "
            "or from the tray menu at any time.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        ok, message = install_gnome_shortcut(self.config.hotkey)
        self.tray.show_message(
            "Mystic Pointer shortcut" if ok else "Shortcut not installed",
            message,
            9000,
        )

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True

        self.wiggle_thread.stop()
        self.hotkey_listener.stop()
        overlay = self.active_overlay
        self.active_overlay = None
        if overlay is not None:
            try:
                overlay.close()
            except RuntimeError:
                # Already deleted by Qt.
                pass
        self.activation_server.close()
        self.capture_service.shutdown()
        self.qapp.quit()


def main() -> None:
    args = [arg for arg in sys.argv if arg != "--activate"]
    activate_on_start = len(args) != len(sys.argv)

    # A system shortcut runs "mystic-pointer --activate": forward it to the tray
    # process instead of starting a second copy of the application.
    if activate_on_start:
        from mystic_pointer.ipc import notify_running_instance

        if notify_running_instance():
            return

    # High DPI scaling and Qt platform settings
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(args)
    app.setApplicationName("MysticPointer")
    app.setApplicationDisplayName("Mystic Pointer")
    app.setOrganizationName("MysticPointer")
    app.setQuitOnLastWindowClosed(False)

    controller = MysticPointerApp(app, activation_only=activate_on_start)
    controller.start()

    if activate_on_start:
        QTimer.singleShot(0, controller.activate_mystic_pointer)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
