"""Cross-platform global hotkey listener for Mystic Pointer.

Windows: native RegisterHotKey on a dedicated thread.

Linux: applications cannot register global shortcuts on Wayland, and X11 would
need an extra grab library.  Instead, Mystic Pointer exposes ``--activate`` and
installs a GNOME custom keybinding (see ``mystic_pointer.shortcut``), so the
listener is a no-op there.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QThread, Signal

_MODIFIERS = {
    "ctrl": 0x0002,  # MOD_CONTROL
    "control": 0x0002,
    "alt": 0x0001,
    "shift": 0x0004,
    "super": 0x0008,
    "win": 0x0008,
    "meta": 0x0008,
}

_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "escape": 0x1B,
    "esc": 0x1B,
    "delete": 0x2E,
    "backspace": 0x08,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
}


def parse_hotkey(hotkey: str) -> tuple[int, int] | None:
    """Parse ``Ctrl+Alt+G`` into ``(modifiers, virtual_key)`` for Windows."""
    parts = [part.strip() for part in hotkey.replace("+", " ").split() if part.strip()]
    if len(parts) < 2:
        return None

    modifiers = 0
    virtual_key: int | None = None
    for part in parts:
        lowered = part.lower()
        if lowered in _MODIFIERS:
            modifiers |= _MODIFIERS[lowered]
            continue
        if virtual_key is not None:
            return None
        if lowered in _KEYS:
            virtual_key = _KEYS[lowered]
        elif len(part) == 1 and part.isalnum():
            virtual_key = ord(part.upper())
        elif lowered.startswith("f") and lowered[1:].isdigit():
            number = int(lowered[1:])
            if not 1 <= number <= 24:
                return None
            virtual_key = 0x70 + number - 1  # VK_F1
        else:
            return None

    if virtual_key is None or modifiers == 0:
        return None
    return modifiers, virtual_key


class GlobalHotkeyListener(QObject):
    """Listens for the global activation hotkey on platforms that support it."""

    activated = Signal()

    def __init__(self, hotkey_str: str = "Ctrl+Alt+G", parent: QObject | None = None):
        super().__init__(parent)
        self.hotkey_str = hotkey_str
        self._thread: HotkeyWorkerThread | None = None

    @property
    def supported(self) -> bool:
        return sys.platform == "win32"

    def start(self) -> None:
        if not self.supported:
            return
        if self._thread is not None and self._thread.isRunning():
            return

        self._thread = HotkeyWorkerThread(self.hotkey_str)
        self._thread.hotkey_triggered.connect(self.activated.emit)
        self._thread.start()

    def stop(self) -> None:
        if self._thread is not None:
            self._thread.stop()
            self._thread = None

    def set_hotkey(self, hotkey_str: str) -> None:
        if hotkey_str == self.hotkey_str:
            return
        self.hotkey_str = hotkey_str
        self.stop()
        self.start()


class HotkeyWorkerThread(QThread):
    hotkey_triggered = Signal()

    def __init__(self, hotkey_str: str, parent: QObject | None = None):
        super().__init__(parent)
        self.hotkey_str = hotkey_str
        self._running = False

    def run(self) -> None:
        self._running = True
        if sys.platform == "win32":
            self._run_windows()
        # Linux uses a system keybinding that calls "mystic-pointer --activate".

    def _run_windows(self) -> None:
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            parsed = parse_hotkey(self.hotkey_str)
            if parsed is None:
                print(f"[Hotkey] Unsupported shortcut: {self.hotkey_str}")
                return
            modifiers, virtual_key = parsed
            hotkey_id = 1001

            if not user32.RegisterHotKey(None, hotkey_id, modifiers, virtual_key):
                print(f"[Hotkey] Could not register Windows global hotkey {self.hotkey_str}")
                return

            msg = wintypes.MSG()
            try:
                while self._running:
                    # Blocking GetMessage would never observe _running becoming
                    # False, so peek with a short timeout instead.
                    if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                        if msg.message == 0x0312:  # WM_HOTKEY
                            self.hotkey_triggered.emit()
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
                    self.msleep(30)
            finally:
                user32.UnregisterHotKey(None, hotkey_id)
        except Exception as e:
            print(f"[Hotkey] Windows hotkey error: {e}")

    def stop(self) -> None:
        self._running = False
        self.wait(1000)
