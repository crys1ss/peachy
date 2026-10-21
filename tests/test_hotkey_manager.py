"""Unit tests for core/hotkey_manager.py with win32 mocked."""

from unittest.mock import MagicMock, patch
import pytest

from core.hotkey_manager import HotkeyManager


def test_hotkey_registration_success(qapp, monkeypatch):
    """Test successful hotkey registration path."""
    mock_reg = MagicMock(return_value=True)
    monkeypatch.setattr("core.win32.register_hotkey", mock_reg)

    hm = HotkeyManager()
    failed_signals = []
    hm.registration_failed.connect(failed_signals.append)

    assert hm.register("Ctrl+Shift+Space") is True
    assert hm.is_registered is True
    assert hm.current_shortcut == "Ctrl+Shift+Space"
    assert len(failed_signals) == 0

    mock_reg.assert_called_once()
    hm.cleanup()


def test_hotkey_registration_failure(qapp, monkeypatch):
    """Test hotkey registration failure path when shortcut is in use by another app."""
    mock_reg = MagicMock(return_value=False)
    monkeypatch.setattr("core.win32.register_hotkey", mock_reg)

    hm = HotkeyManager()
    failed_signals = []
    hm.registration_failed.connect(failed_signals.append)

    assert hm.register("Alt+Q") is False
    assert hm.is_registered is False
    assert len(failed_signals) == 1
    assert "Failed to register hotkey" in failed_signals[0]

    hm.cleanup()


def test_hotkey_pause_and_resume(qapp, monkeypatch):
    """Test pausing unregisters from OS and unpausing re-registers."""
    mock_reg = MagicMock(return_value=True)
    mock_unreg = MagicMock(return_value=True)
    monkeypatch.setattr("core.win32.register_hotkey", mock_reg)
    monkeypatch.setattr("core.win32.unregister_hotkey", mock_unreg)

    hm = HotkeyManager()
    hm.register("Ctrl+Shift+Space")
    assert hm.is_registered is True

    # Pause
    hm.set_paused(True)
    assert hm.is_paused is True
    assert hm.is_registered is False
    mock_unreg.assert_called_once()

    # Resume
    mock_reg.reset_mock()
    hm.set_paused(False)
    assert hm.is_paused is False
    assert hm.is_registered is True
    mock_reg.assert_called_once()

    hm.cleanup()


def test_hotkey_triggered_signal(qapp):
    """Test signal dispatch on hotkey trigger and suppression when paused."""
    hm = HotkeyManager()
    triggered_count = []
    hm.hotkey_triggered.connect(lambda: triggered_count.append(1))

    # Triggered while active
    hm._handle_hotkey()
    assert len(triggered_count) == 1

    # Triggered while paused -> suppressed
    hm.set_paused(True)
    hm._handle_hotkey()
    assert len(triggered_count) == 1

    hm.cleanup()
