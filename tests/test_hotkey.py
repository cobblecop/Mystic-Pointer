"""Tests for the Windows hotkey parser."""

from mystic_pointer.core.hotkey import parse_hotkey


def test_parse_default_hotkey():
    assert parse_hotkey("Ctrl+Alt+G") == (0x0002 | 0x0001, ord("G"))


def test_parse_shift_and_function_key():
    assert parse_hotkey("Ctrl+Shift+F9") == (0x0002 | 0x0004, 0x70 + 8)


def test_parse_invalid_hotkeys():
    assert parse_hotkey("G") is None
    assert parse_hotkey("Ctrl+Alt") is None
    assert parse_hotkey("Ctrl+Alt+NotAKey") is None
