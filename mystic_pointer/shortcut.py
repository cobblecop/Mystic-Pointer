"""Optional helper that installs a GNOME system shortcut for Mystic Pointer.

Unlike X11/Windows, Wayland does not allow applications to register global
hotkeys themselves.  GNOME stores system shortcuts in gsettings, so we can add
one on the user's behalf (with their explicit confirmation) that calls
``mystic-pointer --activate``.
"""

from __future__ import annotations

import ast
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

_MEDIA_KEYS_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
_CUSTOM_KEYBINDINGS = f"{_MEDIA_KEYS_SCHEMA}.custom-keybinding"
_CUSTOM_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/mystic-pointer/"
_SHORTCUT_NAME = "Mystic Pointer"

_MODIFIERS = {
    "ctrl": "<Control>",
    "control": "<Control>",
    "alt": "<Alt>",
    "option": "<Alt>",
    "shift": "<Shift>",
    "super": "<Super>",
    "meta": "<Super>",
    "win": "<Super>",
    "cmd": "<Super>",
    "command": "<Super>",
}

_KEYS = {
    "space": "space",
    "enter": "Return",
    "return": "Return",
    "tab": "Tab",
    "escape": "Escape",
    "esc": "Escape",
    "delete": "Delete",
    "backspace": "BackSpace",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
}


def gtk_accelerator(hotkey: str) -> str | None:
    """Convert ``Ctrl+Alt+G`` to the GTK form ``<Control><Alt>g``."""
    parts = [part.strip() for part in hotkey.replace("+", " ").split() if part.strip()]
    if len(parts) < 2:
        return None

    modifiers: list[str] = []
    key: str | None = None
    for part in parts:
        lowered = part.lower()
        if lowered in _MODIFIERS:
            modifier = _MODIFIERS[lowered]
            if modifier not in modifiers:
                modifiers.append(modifier)
            continue
        if key is not None:
            return None
        if lowered in _KEYS:
            key = _KEYS[lowered]
        elif len(part) == 1:
            key = part.lower()
        elif lowered.startswith("f") and lowered[1:].isdigit():
            key = f"F{lowered[1:]}"
        else:
            return None

    if key is None or not modifiers:
        return None
    return "".join(modifiers) + key


def _activation_command() -> str:
    console_script = shutil.which("mystic-pointer")
    if console_script:
        return f'"{console_script}" --activate'

    main_py = Path(__file__).resolve().parent.parent / "main.py"
    if main_py.exists():
        return f'"{sys.executable}" "{main_py}" --activate'
    return f'"{sys.executable}" -m mystic_pointer.app --activate'


def _gsettings_get(schema: str, key: str) -> str | None:
    try:
        result = subprocess.run(
            ["gsettings", "get", schema, key],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _command_is_usable(command: str) -> bool:
    """Whether a stored shortcut command still points at a real launcher.

    The command is a shell-like string such as
    ``"/path/.venv/bin/python" "/path/main.py" --activate``.  A bare program
    name is left alone (it resolves through ``PATH``); an absolute executable
    that no longer exists means the environment was moved or deleted.
    """
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if not parts:
        return False
    executable = parts[0]
    if os.path.isabs(executable):
        return os.path.exists(executable)
    return True


def _gvariant_string(value: str) -> str:
    """Serialize a string the way ``gsettings set`` expects it.

    ``gsettings set`` takes a GVariant value, so a command such as
    ``"/path/python" "/path/main.py" --activate`` must be wrapped in quotes.
    Without this, GNOME rejects the value ("expected end of input") and the
    shortcut keeps an empty command.
    """
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _gsettings_set(schema: str, key: str, value: str) -> bool:
    try:
        result = subprocess.run(
            ["gsettings", "set", schema, key, value],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _parse_string_list(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    # gsettings prints an empty array as "@as []".
    if raw.startswith("@as "):
        raw = raw[4:].strip()
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None
    if not isinstance(value, list):
        return None
    return [str(item) for item in value]


def _parse_string(raw: str | None) -> str | None:
    """Read a GVariant string as printed by ``gsettings get``."""
    if raw is None:
        return None
    try:
        value = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None
    return value if isinstance(value, str) else None


def is_gnome_desktop() -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    return "gnome" in desktop or "unity" in desktop


def install_gnome_shortcut(hotkey: str = "Ctrl+Alt+G") -> tuple[bool, str]:
    """Add or update a GNOME custom keybinding for Mystic Pointer."""
    if not is_gnome_desktop():
        return False, "Automatic shortcut setup is only available on GNOME."
    if shutil.which("gsettings") is None:
        return False, "The 'gsettings' tool is not installed."

    accelerator = gtk_accelerator(hotkey)
    if accelerator is None:
        return False, f"'{hotkey}' is not a valid shortcut. Use e.g. Ctrl+Alt+G."

    existing = _parse_string_list(_gsettings_get(_MEDIA_KEYS_SCHEMA, "custom-keybindings"))
    if existing is None:
        return False, "Could not read the current GNOME shortcut list; no changes were made."

    paths = list(existing)
    if _CUSTOM_PATH not in paths:
        paths.append(_CUSTOM_PATH)
        serialized = "[" + ", ".join(repr(path) for path in paths) + "]"
        if not _gsettings_set(_MEDIA_KEYS_SCHEMA, "custom-keybindings", serialized):
            return False, "GNOME rejected the updated shortcut list."

    schema = f"{_CUSTOM_KEYBINDINGS}:{_CUSTOM_PATH}"
    updates = (
        ("name", _gvariant_string(_SHORTCUT_NAME)),
        ("command", _gvariant_string(_activation_command())),
        ("binding", _gvariant_string(accelerator)),
    )
    for key, value in updates:
        if not _gsettings_set(schema, key, value):
            return False, f"Could not set the '{key}' property of the shortcut."

    return True, (
        f"Shortcut {hotkey} is now active. You can review it in "
        "GNOME Settings → Keyboard → Custom Shortcuts."
    )


def repair_gnome_shortcut(hotkey: str = "Ctrl+Alt+G") -> tuple[bool, str]:
    """Repair an existing Mystic Pointer shortcut that does nothing.

    A custom keybinding can be registered while its ``command`` or ``binding``
    is still empty -- for example when it was created by hand in GNOME Settings
    or by an older Mystic Pointer version.  Such a shortcut appears in the list
    but pressing it has no effect.  This fills in the missing pieces and never
    adds a new shortcut or overrides a binding the user already chose.

    Returns ``(changed, message)``.
    """
    if not is_gnome_desktop():
        return False, "Automatic shortcut repair is only available on GNOME."
    if shutil.which("gsettings") is None:
        return False, "The 'gsettings' tool is not installed."

    existing = _parse_string_list(_gsettings_get(_MEDIA_KEYS_SCHEMA, "custom-keybindings"))
    if existing is None:
        return False, "Could not read the current GNOME shortcut list."
    if _CUSTOM_PATH not in existing:
        return False, "The Mystic Pointer shortcut is not installed."

    schema = f"{_CUSTOM_KEYBINDINGS}:{_CUSTOM_PATH}"
    name = _parse_string(_gsettings_get(schema, "name")) or ""
    command = (_parse_string(_gsettings_get(schema, "command")) or "").strip()
    binding = (_parse_string(_gsettings_get(schema, "binding")) or "").strip()

    updates: list[tuple[str, str]] = []
    if not name:
        updates.append(("name", _gvariant_string(_SHORTCUT_NAME)))
    if not command or not _command_is_usable(command):
        updates.append(("command", _gvariant_string(_activation_command())))
    if not binding:
        accelerator = gtk_accelerator(hotkey)
        if accelerator is None:
            return False, f"'{hotkey}' is not a valid shortcut. Use e.g. Ctrl+Alt+G."
        updates.append(("binding", _gvariant_string(accelerator)))

    if not updates:
        return False, "The Mystic Pointer shortcut is already configured."

    for key, value in updates:
        if not _gsettings_set(schema, key, value):
            return False, f"Could not set the '{key}' property of the shortcut."

    repaired = ", ".join(key for key, _value in updates)
    return True, (
        f"The existing Mystic Pointer shortcut was incomplete; repaired {repaired}. "
        f"Press {hotkey} to activate Mystic Pointer."
    )


def uninstall_gnome_shortcut() -> tuple[bool, str]:
    """Remove the shortcut added by :func:`install_gnome_shortcut`."""
    if not is_gnome_desktop() or shutil.which("gsettings") is None:
        return False, "GNOME shortcut removal is not available."

    existing = _parse_string_list(_gsettings_get(_MEDIA_KEYS_SCHEMA, "custom-keybindings"))
    if existing is None:
        return False, "Could not read the current GNOME shortcut list."
    if _CUSTOM_PATH not in existing:
        return True, "The Mystic Pointer shortcut is not installed."

    paths = [path for path in existing if path != _CUSTOM_PATH]
    serialized = "[" + ", ".join(repr(path) for path in paths) + "]"
    if not _gsettings_set(_MEDIA_KEYS_SCHEMA, "custom-keybindings", serialized):
        return False, "GNOME rejected the updated shortcut list."
    return True, "The Mystic Pointer shortcut was removed."
