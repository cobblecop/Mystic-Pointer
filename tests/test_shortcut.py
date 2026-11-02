"""Tests for the GNOME shortcut helper (no system changes are made)."""

import mystic_pointer.shortcut as shortcut
from mystic_pointer.shortcut import (
    _gvariant_string,
    _parse_string,
    _parse_string_list,
    gtk_accelerator,
)


def test_gtk_accelerator_parses_default_hotkey():
    assert gtk_accelerator("Ctrl+Alt+G") == "<Control><Alt>g"


def test_gtk_accelerator_supports_super_and_function_keys():
    assert gtk_accelerator("Super+G") == "<Super>g"
    assert gtk_accelerator("Ctrl+Shift+F9") == "<Control><Shift>F9"


def test_gtk_accelerator_rejects_incomplete_or_unknown_keys():
    assert gtk_accelerator("G") is None
    assert gtk_accelerator("Ctrl+Alt+NotAKeyName") is None
    assert gtk_accelerator("Ctrl+Alt+G+H") is None


def test_parse_string_list_handles_gsettings_output():
    assert _parse_string_list("@as []") == []
    assert _parse_string_list("['/org/example/a/', '/org/example/b/']") == [
        "/org/example/a/",
        "/org/example/b/",
    ]
    assert _parse_string_list("not a list") is None


def test_parse_string_handles_gsettings_output():
    assert _parse_string("'Mystic Pointer'") == "Mystic Pointer"
    assert _parse_string("''") == ""
    assert _parse_string("not a string") is None


def test_gvariant_string_quotes_commands():
    # A command with spaces and inner quotes must be one GVariant string, or
    # gsettings rejects it and the shortcut keeps an empty command.
    value = _gvariant_string('"/p/python" "/p/main.py" --activate')
    assert value == '\'"/p/python" "/p/main.py" --activate\''
    assert _gvariant_string("Mystic Pointer") == "'Mystic Pointer'"
    assert _gvariant_string("it's") == "'it\\'s'"


def _repair_fixture(monkeypatch, values: dict[tuple[str, str], str | None]):
    schema = f"{shortcut._CUSTOM_KEYBINDINGS}:{shortcut._CUSTOM_PATH}"
    writes: dict[tuple[str, str], str] = {}

    monkeypatch.setattr(shortcut, "is_gnome_desktop", lambda: True)
    monkeypatch.setattr(shortcut.shutil, "which", lambda _name: "/usr/bin/gsettings")
    monkeypatch.setattr(shortcut, "_gsettings_get", lambda s, k: values.get((s, k)))
    monkeypatch.setattr(
        shortcut,
        "_gsettings_set",
        lambda s, k, v: writes.__setitem__((s, k), v) or True,
    )
    monkeypatch.setattr(
        shortcut,
        "_activation_command",
        lambda: '"/project/.venv/bin/python" "/project/main.py" --activate',
    )
    return schema, writes


def test_repair_fills_in_an_empty_command_and_binding(monkeypatch):
    schema, writes = _repair_fixture(
        monkeypatch,
        {
            (shortcut._MEDIA_KEYS_SCHEMA, "custom-keybindings"): (f"['{shortcut._CUSTOM_PATH}']"),
            (f"{shortcut._CUSTOM_KEYBINDINGS}:{shortcut._CUSTOM_PATH}", "name"): (
                "'Mystic Pointer'"
            ),
            (f"{shortcut._CUSTOM_KEYBINDINGS}:{shortcut._CUSTOM_PATH}", "command"): "''",
            (f"{shortcut._CUSTOM_KEYBINDINGS}:{shortcut._CUSTOM_PATH}", "binding"): "''",
        },
    )

    changed, message = shortcut.repair_gnome_shortcut("Ctrl+Alt+G")

    assert changed
    assert "Ctrl+Alt+G" in message
    assert "--activate" in writes[(schema, "command")]
    assert writes[(schema, "command")].startswith("'\"")
    assert writes[(schema, "binding")] == "'<Control><Alt>g'"
    # A name that is already set is left alone.
    assert (schema, "name") not in writes


def test_repair_replaces_a_command_from_a_missing_environment(monkeypatch):
    schema, writes = _repair_fixture(
        monkeypatch,
        {
            (shortcut._MEDIA_KEYS_SCHEMA, "custom-keybindings"): (f"['{shortcut._CUSTOM_PATH}']"),
            (f"{shortcut._CUSTOM_KEYBINDINGS}:{shortcut._CUSTOM_PATH}", "name"): (
                "'Mystic Pointer'"
            ),
            (f"{shortcut._CUSTOM_KEYBINDINGS}:{shortcut._CUSTOM_PATH}", "command"): (
                '\'"/definitely/gone/python" "/definitely/gone/main.py" --activate\''
            ),
            (f"{shortcut._CUSTOM_KEYBINDINGS}:{shortcut._CUSTOM_PATH}", "binding"): (
                "'<Control><Alt>g'"
            ),
        },
    )

    changed, _message = shortcut.repair_gnome_shortcut("Ctrl+Alt+G")

    assert changed
    assert writes[(schema, "command")].startswith("'\"")
    assert (schema, "binding") not in writes


def test_repair_leaves_a_complete_shortcut_alone(monkeypatch):
    schema, writes = _repair_fixture(
        monkeypatch,
        {
            (shortcut._MEDIA_KEYS_SCHEMA, "custom-keybindings"): (f"['{shortcut._CUSTOM_PATH}']"),
            (f"{shortcut._CUSTOM_KEYBINDINGS}:{shortcut._CUSTOM_PATH}", "name"): (
                "'Mystic Pointer'"
            ),
            (f"{shortcut._CUSTOM_KEYBINDINGS}:{shortcut._CUSTOM_PATH}", "command"): (
                "'mystic-pointer --activate'"
            ),
            (f"{shortcut._CUSTOM_KEYBINDINGS}:{shortcut._CUSTOM_PATH}", "binding"): ("'<Super>g'"),
        },
    )

    changed, _message = shortcut.repair_gnome_shortcut("Ctrl+Alt+G")

    assert not changed
    assert writes == {}
    assert (schema, "binding") not in writes


def test_repair_does_not_add_a_missing_shortcut(monkeypatch):
    schema, writes = _repair_fixture(
        monkeypatch,
        {(shortcut._MEDIA_KEYS_SCHEMA, "custom-keybindings"): "@as []"},
    )

    changed, _message = shortcut.repair_gnome_shortcut("Ctrl+Alt+G")

    assert not changed
    assert writes == {}
    assert (schema, "command") not in writes
