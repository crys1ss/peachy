"""Unit tests for Peachy SettingsWindow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
import pytest

from config.settings import Settings
from ui.settings_window import SettingsWindow, ShortcutRecorderButton


def test_settings_window_initialization(qtbot):
    """Verify SettingsWindow initializes and loads current settings values into UI."""
    test_settings = Settings(
        hotkey="Ctrl+Alt+P",
        model="gemini-3.5-flash",
        pinned=True,
        double_tap_enabled=True,
        double_tap_interval_ms=320,
        popup_position="last_used",
    )

    with patch("config.key_storage.get_api_key", return_value="fake-secret-key-123"), \
         patch("config.key_storage.get_key_source", return_value="keyring"), \
         patch("ui.settings_window.is_launch_at_startup_enabled", return_value=True):

        win = SettingsWindow(settings=test_settings)
        qtbot.addWidget(win)

        assert win.shortcut_button.text() == "Ctrl+Alt+P"
        assert win.double_tap_check.isChecked() is True
        assert win.interval_slider.value() == 320
        assert win.interval_slider.isEnabled() is True
        assert win.pinned_check.isChecked() is True
        assert win.pos_last.isChecked() is True
        assert win.startup_check.isChecked() is True
        assert win.mode_freehand.isChecked() is True
        assert win.shape_blank.isChecked() is True
        assert win.key_input.text() == "fake-secret-key-123"


def test_shortcut_recorder_button(qtbot):
    """Verify ShortcutRecorderButton enters recording state and captures key combination."""
    btn = ShortcutRecorderButton("Ctrl+Shift+Space")
    qtbot.addWidget(btn)

    # Click to record
    btn.click()
    assert btn.is_recording is True
    assert "Press keys" in btn.text()

    # Simulate pressing Ctrl+Alt+K
    key_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_K,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        "k",
    )
    btn.keyPressEvent(key_event)

    assert btn.is_recording is False
    assert btn.current_shortcut == "Ctrl+Alt+K"
    assert btn.text() == "Ctrl+Alt+K"


def test_shortcut_recorder_escape_cancels(qtbot):
    """Verify Esc key exits recording without changing shortcut."""
    btn = ShortcutRecorderButton("Ctrl+Shift+Space")
    qtbot.addWidget(btn)

    btn.click()
    assert btn.is_recording is True

    esc_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    btn.keyPressEvent(esc_event)

    assert btn.is_recording is False
    assert btn.current_shortcut == "Ctrl+Shift+Space"


def test_save_with_hotkey_conflict_keeps_old_shortcut(qtbot):
    """Verify hotkey conflict keeps old shortcut and shows inline message."""
    test_settings = Settings(hotkey="Ctrl+Shift+Space")
    mock_hotkey_manager = MagicMock()
    # Registration fails (conflict)
    mock_hotkey_manager.register.return_value = False

    win = SettingsWindow(settings=test_settings, hotkey_manager=mock_hotkey_manager)
    qtbot.addWidget(win)

    # Change shortcut to conflicting one
    win.shortcut_button.current_shortcut = "Ctrl+C"

    # Attempt save
    win._save_and_apply()

    # Manager called with new shortcut
    mock_hotkey_manager.register.assert_called_once_with("Ctrl+C")
    # Inline conflict message shown
    assert "Conflict" in win.shortcut_status_label.text()
    # Old shortcut kept
    assert win.shortcut_button.current_shortcut == "Ctrl+Shift+Space"
    assert win.settings.hotkey == "Ctrl+Shift+Space"


def test_save_and_apply_success(qtbot):
    """Verify successful save updates settings and calls key_storage & winreg."""
    test_settings = Settings(hotkey="Ctrl+Shift+Space")
    mock_hotkey_manager = MagicMock()
    mock_hotkey_manager.register.return_value = True

    mock_double_tap = MagicMock()

    with patch("ui.settings_window.save_settings") as mock_save, \
         patch("config.key_storage.set_api_key") as mock_set_key, \
         patch("ui.settings_window.set_launch_at_startup") as mock_startup:

        win = SettingsWindow(
            settings=test_settings,
            hotkey_manager=mock_hotkey_manager,
            double_tap_hook=mock_double_tap,
        )
        qtbot.addWidget(win)

        win.shortcut_button.current_shortcut = "Alt+Q"
        win.double_tap_check.setChecked(True)
        win.interval_slider.setValue(350)
        win.key_input.setText("new-secret-token")
        win.pos_near.setChecked(True)
        win.mode_rect.setChecked(True)
        win.shape_keep.setChecked(True)

        win._save_and_apply()

        assert test_settings.hotkey == "Alt+Q"
        assert test_settings.double_tap_enabled is True
        assert test_settings.double_tap_interval_ms == 350
        assert test_settings.popup_position == "near_selection"
        assert test_settings.selection_mode == "rectangle"
        assert test_settings.outside_shape == "keep"

        mock_save.assert_called_once()
        mock_set_key.assert_called_once_with("new-secret-token")
        mock_double_tap.set_interval.assert_called_once_with(350)
        mock_double_tap.set_enabled.assert_called_once_with(True)
