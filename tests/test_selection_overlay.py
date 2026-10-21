"""Unit and integration tests for selection overlay behavior and state flow."""

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication

from capture.screen_capture import CapturedMonitor
from capture.selection_overlay import SelectionOverlayManager, SelectionOverlayWindow
from core.state_manager import AppState, StateManager


def make_dummy_monitor(width: int = 800, height: int = 600, dpr: float = 1.0) -> CapturedMonitor:
    """Create a synthetic CapturedMonitor for unit testing without live display dependencies."""
    app = QApplication.instance()
    screen = app.primaryScreen()

    img = QImage(width, height, QImage.Format_ARGB32)
    img.fill(QColor(100, 150, 200))
    pix = QPixmap.fromImage(img)

    return CapturedMonitor(
        screen=screen,
        name="DummyDisplay",
        logical_geom=(0, 0, int(width / dpr), int(height / dpr)),
        dpr=dpr,
        pixmap=pix,
        image=img,
        capture_time_ms=5.0,
    )


def test_overlay_creation_and_close(qtbot):
    """Verify overlay window initializes with correct geometry and flags."""
    mon = make_dummy_monitor(800, 600, 1.0)
    win = SelectionOverlayWindow(mon)
    qtbot.addWidget(win)

    assert win.windowFlags() & Qt.FramelessWindowHint
    assert win.windowFlags() & Qt.WindowStaysOnTopHint
    assert win.cursor().shape() == Qt.CrossCursor

    win.close()


def test_tiny_selection_rejected_on_mouse_release(qtbot):
    """Selection smaller than 8x8 physical pixels must emit cancelled instead of confirmed."""
    mon = make_dummy_monitor(800, 600, 1.0)
    win = SelectionOverlayWindow(mon)
    qtbot.addWidget(win)

    cancelled_called = []
    confirmed_called = []
    win.selection_cancelled.connect(lambda: cancelled_called.append(True))
    win.selection_confirmed.connect(lambda *args: confirmed_called.append(True))

    # Simulate tiny 4x4 drag
    win._is_active_drag = True
    win._start_pos = QPointF(10.0, 10.0)
    win._current_pos = QPointF(14.0, 14.0)
    win._rect_logical = (10.0, 10.0, 4.0, 4.0)

    win._finish_selection()

    assert len(confirmed_called) == 0
    assert len(cancelled_called) == 1


def test_valid_selection_confirmed(qtbot):
    """Selection meeting threshold emits confirmed crop."""
    mon = make_dummy_monitor(800, 600, 1.0)
    win = SelectionOverlayWindow(mon)
    qtbot.addWidget(win)

    confirmed_payload = []
    win.selection_confirmed.connect(lambda crop, m, r: confirmed_payload.append((crop, m, r)))

    # Simulate 50x40 drag
    win._is_active_drag = True
    win._start_pos = QPointF(10.0, 10.0)
    win._current_pos = QPointF(60.0, 50.0)
    win._rect_logical = (10.0, 10.0, 50.0, 40.0)

    win._finish_selection()

    assert len(confirmed_payload) == 1
    crop, m, r = confirmed_payload[0]
    assert crop.width() == 50
    assert crop.height() == 40
    assert r == (10, 10, 50, 40)


def test_esc_key_cancels_selection(qtbot):
    """Pressing Escape on overlay emits selection_cancelled."""
    mon = make_dummy_monitor(800, 600, 1.0)
    win = SelectionOverlayWindow(mon)
    qtbot.addWidget(win)

    cancelled = []
    win.selection_cancelled.connect(lambda: cancelled.append(True))

    qtbot.keyPress(win, Qt.Key_Escape)
    assert len(cancelled) == 1


def test_hotkey_during_selecting_is_ignored():
    """Verify that state machine rejects activation while state is SELECTING."""
    sm = StateManager()
    sm.transition_to(AppState.CAPTURING)
    sm.transition_to(AppState.SELECTING)
    assert sm.state == AppState.SELECTING

    # Attempting to activate while SELECTING
    assert sm.can_activate() is False
    assert sm.request_activation() is False
    assert sm.state == AppState.SELECTING


def test_cancellation_returns_to_idle():
    """Verify that cancellation returns application to IDLE state."""
    sm = StateManager()
    sm.transition_to(AppState.CAPTURING)
    sm.transition_to(AppState.SELECTING)

    # Simulating cancellation in controller
    assert sm.transition_to(AppState.IDLE) is True
    assert sm.state == AppState.IDLE
    assert sm.is_idle is True
