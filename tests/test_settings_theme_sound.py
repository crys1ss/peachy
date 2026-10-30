"""Unit tests verifying theme_mode propagation, theme switching, and SettingsWindow appearance & sound controls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
import pytest

from config.settings import Settings
from ui.history_window import HistoryWindow
from ui.peachy_popup import PeachyPopup
from ui.settings_window import SettingsWindow
from ui.sound import get_sound_manager
from ui.theme import ThemeTokens, get_theme


def test_get_theme_mode_propagation_popup(qtbot):
    """Verify PeachyPopup receives theme_mode=settings.theme."""
    s_light = Settings(theme="light")
    popup_light = PeachyPopup(settings=s_light)
    qtbot.addWidget(popup_light)
    assert popup_light.theme.name == "light"

    s_midnight = Settings(theme="midnight")
    popup_mid = PeachyPopup(settings=s_midnight)
    qtbot.addWidget(popup_mid)
    assert popup_mid.theme.name == "midnight"


def test_popup_apply_theme_live(qtbot):
    """Verify PeachyPopup.apply_theme dynamically switches between themes."""
    popup = PeachyPopup(settings=Settings(theme="midnight"))
    qtbot.addWidget(popup)
    assert popup.theme.name == "midnight"

    # Switch to light
    popup.apply_theme("light")
    assert popup.theme.name == "light"

    # Switch back to midnight
    popup.apply_theme("midnight")
    assert popup.theme.name == "midnight"


def test_get_theme_mode_propagation_history_window(qtbot):
    """Verify HistoryWindow receives theme_mode=settings.theme."""
    mock_store = MagicMock()
    mock_store.list_conversations.return_value = []

    s_light = Settings(theme="light")
    win_light = HistoryWindow(store=mock_store, settings=s_light)
    qtbot.addWidget(win_light)
    assert win_light.theme.name == "light"

    s_mid = Settings(theme="midnight")
    win_mid = HistoryWindow(store=mock_store, settings=s_mid)
    qtbot.addWidget(win_mid)
    assert win_mid.theme.name == "midnight"

    # Live apply_theme
    win_mid.apply_theme("light")
    assert win_mid.theme.name == "light"


def test_get_theme_mode_propagation_settings_window(qtbot):
    """Verify SettingsWindow receives theme_mode=settings.theme."""
    s_light = Settings(theme="light")
    win_light = SettingsWindow(settings=s_light)
    qtbot.addWidget(win_light)
    assert win_light.theme_tokens.name == "light"

    s_mid = Settings(theme="midnight")
    win_mid = SettingsWindow(settings=s_mid)
    qtbot.addWidget(win_mid)
    assert win_mid.theme_tokens.name == "midnight"

    # Live apply_theme
    win_mid.apply_theme("light")
    assert win_mid.theme_tokens.name == "light"


def test_settings_window_appearance_and_sound_controls_load(qtbot):
    """Verify theme, motion, and sound controls populate accurately from settings."""
    test_settings = Settings(
        theme="light",
        reduce_motion=True,
        sound_enabled=False,
        sound_volume=65,
    )

    win = SettingsWindow(settings=test_settings)
    qtbot.addWidget(win)

    # Check Appearance
    assert win.theme_combo.currentData() == "light"
    assert win.reduce_motion_check.isChecked() is True

    # Check Sound
    assert win.sound_enabled_check.isChecked() is False
    assert win.sound_volume_slider.value() == 65
    assert win.sound_volume_label.text() == "65%"
    # When sound is disabled, slider and test button should be disabled
    assert win.sound_volume_slider.isEnabled() is False
    assert win.test_sound_btn.isEnabled() is False


def test_settings_window_sound_toggle_and_slider(qtbot):
    """Verify sound checkbox toggles controls and slider updates volume label."""
    test_settings = Settings(sound_enabled=True, sound_volume=30)
    win = SettingsWindow(settings=test_settings)
    qtbot.addWidget(win)

    assert win.sound_volume_slider.isEnabled() is True
    assert win.test_sound_btn.isEnabled() is True

    # Change slider value
    win.sound_volume_slider.setValue(85)
    assert win.sound_volume_label.text() == "85%"

    # Uncheck sound enabled
    win.sound_enabled_check.setChecked(False)
    assert win.sound_volume_slider.isEnabled() is False
    assert win.test_sound_btn.isEnabled() is False

    # Check sound enabled
    win.sound_enabled_check.setChecked(True)
    assert win.sound_volume_slider.isEnabled() is True
    assert win.test_sound_btn.isEnabled() is True


def test_settings_window_test_sound_button(qtbot):
    """Verify clicking Test Sound invokes SoundManager."""
    test_settings = Settings(sound_enabled=True, sound_volume=50)
    win = SettingsWindow(settings=test_settings)
    qtbot.addWidget(win)

    sm = get_sound_manager(test_settings)
    with patch.object(sm, "play", return_value=True) as mock_play:
        win.sound_volume_slider.setValue(70)
        win.test_sound_btn.click()
        assert sm.get_volume() == 70
        mock_play.assert_called_once_with("open")


def test_settings_window_save_appearance_and_sound(qtbot):
    """Verify saving settings persists theme, reduce_motion, and sound settings."""
    test_settings = Settings(
        theme="midnight",
        reduce_motion=False,
        sound_enabled=True,
        sound_volume=35,
    )

    with patch("ui.settings_window.save_settings") as mock_save, \
         patch("config.key_storage.set_api_key"), \
         patch("ui.settings_window.set_launch_at_startup"):

        win = SettingsWindow(settings=test_settings)
        qtbot.addWidget(win)

        # Modify values
        idx = win.theme_combo.findData("light")
        win.theme_combo.setCurrentIndex(idx)
        win.reduce_motion_check.setChecked(True)
        win.sound_enabled_check.setChecked(False)
        win.sound_volume_slider.setValue(90)

        win._save_and_apply()

        assert test_settings.theme == "light"
        assert test_settings.reduce_motion is True
        assert test_settings.sound_enabled is False
        assert test_settings.sound_volume == 90

        mock_save.assert_called_once()
        sm = get_sound_manager(test_settings)
        assert sm.is_muted is True
        assert sm.get_volume() == 90
