"""Hardening tests verifying failure resilience, graceful recovery, and crash protection."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QCloseEvent, QImage, QScreen
import pytest

from ai.provider import (
    BlockedError,
    EmptyResponseError,
    InvalidKeyError,
    MissingKeyError,
    NetworkError,
    RateLimitedError,
    TimeoutError,
)
from app import setup_resilient_error_handling
from capture.geometry import is_valid_selection
from capture.screen_capture import CapturedMonitor
from capture.selection_overlay import OverlayManager, SelectionOverlay
from core.app_controller import AppController
from core.state_manager import AppState, StateManager


def test_hardening_error_messages_exact():
    """Verify exact user-friendly wording for all error types specified in Day 5 prompt."""
    assert RateLimitedError.DEFAULT_MESSAGE == "Peachy needs a breather, try again in a moment"
    assert MissingKeyError.DEFAULT_MESSAGE == "Gemini API key is missing. Please add your key in Settings."
    assert NetworkError.DEFAULT_MESSAGE == "You appear to be offline. Please check your internet connection and retry."
    assert InvalidKeyError.DEFAULT_MESSAGE == "Gemini API key is invalid or unauthorized. Please verify your key."
    assert TimeoutError.DEFAULT_MESSAGE == "Request to Gemini timed out. Please check your network connection and retry."
    assert BlockedError.DEFAULT_MESSAGE == "Content was blocked by safety filters. Please try a different selection."
    assert EmptyResponseError.DEFAULT_MESSAGE == "Gemini returned an empty response. Try rephrasing your question."


def test_tiny_selection_rejected():
    """Verify selections below 8x8 physical pixels are rejected without firing confirm."""
    # 7x7 rejected
    assert is_valid_selection(7, 7, 8, 8) is False
    assert is_valid_selection(0, 10, 8, 8) is False
    assert is_valid_selection(10, 5, 8, 8) is False
    # 8x8 accepted
    assert is_valid_selection(8, 8, 8, 8) is True
    assert is_valid_selection(100, 100, 8, 8) is True


def test_overlay_closed_by_alt_f4(qtbot):
    """Verify closing overlay via Alt+F4 cancels selection and restores foreground."""
    from tests.test_selection_overlay import create_mock_monitor
    captured = create_mock_monitor(100, 100, dpr=1.0)

    manager = OverlayManager()
    qtbot.addWidget(manager)

    with patch("core.win32.set_foreground_window") as mock_set_fg:
        manager.start_selection([captured], foreground_hwnd=998877)
        overlay = manager.overlays[0]

        cancelled_spy = []
        manager.cancelled.connect(lambda: cancelled_spy.append(True))

        # Simulate Alt+F4 sending QCloseEvent
        close_event = QCloseEvent()
        overlay.closeEvent(close_event)

        assert len(cancelled_spy) == 1
        mock_set_fg.assert_called_with(998877)


def test_monitor_topology_change_during_selection(qtbot):
    """Verify screen change while selecting cancels safely without crashing."""
    from tests.test_selection_overlay import create_mock_monitor
    captured = create_mock_monitor(100, 100, dpr=1.0)

    manager = OverlayManager()
    qtbot.addWidget(manager)

    manager.start_selection([captured], foreground_hwnd=54321)
    assert len(manager.overlays) == 1

    cancelled_called = []
    manager.cancelled.connect(lambda: cancelled_called.append(True))

    # Signal topology change
    manager._on_screens_changed()

    assert len(cancelled_called) == 1
    assert len(manager.overlays) == 0


def test_global_excepthook_resets_to_idle(qtbot):
    """Verify sys.excepthook logs unhandled exceptions, shows toast, and resets FSM to IDLE."""
    mock_app = MagicMock()
    mock_app.state_manager.reset_to_idle = MagicMock()
    mock_app.tray_manager.show_notification = MagicMock()

    setup_resilient_error_handling(mock_app)

    # Trigger artificial unhandled exception via sys.excepthook
    try:
        raise RuntimeError("Simulated unhandled slot exception")
    except RuntimeError:
        exc_type, exc_val, exc_tb = sys.exc_info()
        sys.excepthook(exc_type, exc_val, exc_tb)

    mock_app.state_manager.reset_to_idle.assert_called_once()
    mock_app.tray_manager.show_notification.assert_called_once_with(
        "Peachy Recovered",
        "An unexpected error occurred and was safely logged.",
    )


def test_quitting_while_request_runs_aborts_cleanly(qtbot):
    """Verify quitting during active AI request cleanly terminates worker and releases resources."""
    state_mgr = StateManager()
    hotkey_mgr = MagicMock()
    tray_mgr = MagicMock()
    overlay_mgr = MagicMock()
    popup = MagicMock()

    controller = AppController(
        state_manager=state_mgr,
        hotkey_manager=hotkey_mgr,
        tray_manager=tray_mgr,
        overlay_manager=overlay_mgr,
        popup=popup,
    )

    # Simulate active running worker
    mock_worker = MagicMock()
    mock_worker.isRunning.return_value = True
    controller._active_worker = mock_worker

    # Call shutdown
    controller.shutdown()

    mock_worker.cancel.assert_called_once()
    mock_worker.terminate.assert_called_once()
    mock_worker.wait.assert_called_once()
    assert controller._active_worker is None
    popup.close.assert_called_once()
    overlay_mgr.cleanup.assert_called_once()
