"""Unit tests for shortcut parsing in core/hotkey_manager.py."""

import pytest
from core import win32
from core.hotkey_manager import parse_shortcut


def test_parse_default_shortcut():
    """Test parsing the default shortcut 'Ctrl+Shift+Space'."""
    modifiers, vk = parse_shortcut("Ctrl+Shift+Space")
    assert modifiers & win32.MOD_CONTROL
    assert modifiers & win32.MOD_SHIFT
    assert modifiers & win32.MOD_NOREPEAT
    assert not (modifiers & win32.MOD_ALT)
    assert vk == 0x20  # VK_SPACE


def test_parse_alt_q():
    """Test parsing 'Alt+Q'."""
    modifiers, vk = parse_shortcut("Alt+Q")
    assert modifiers & win32.MOD_ALT
    assert modifiers & win32.MOD_NOREPEAT
    assert not (modifiers & win32.MOD_CONTROL)
    assert vk == ord("Q")


def test_parse_case_insensitivity_and_whitespace():
    """Test case insensitivity and extra whitespace."""
    modifiers, vk = parse_shortcut("  ctrl +  alt +  f12 ")
    assert modifiers & win32.MOD_CONTROL
    assert modifiers & win32.MOD_ALT
    assert modifiers & win32.MOD_NOREPEAT
    assert vk == 0x70 + 11  # F12 VK code


def test_parse_win_key():
    """Test Windows key parsing."""
    modifiers, vk = parse_shortcut("Win+Shift+S")
    assert modifiers & win32.MOD_WIN
    assert modifiers & win32.MOD_SHIFT
    assert vk == ord("S")


@pytest.mark.parametrize(
    "invalid_shortcut",
    [
        "",
        "   ",
        "Ctrl",
        "Ctrl+Shift",
        "Alt+Shift+Win",
        "Ctrl+Shift+A+B",  # Multiple non-modifier keys
        "Ctrl+UnknownKey123",
        "+++",
    ],
)
def test_parse_invalid_shortcuts(invalid_shortcut):
    """Ensure invalid shortcuts raise ValueError with clear message."""
    with pytest.raises(ValueError):
        parse_shortcut(invalid_shortcut)
