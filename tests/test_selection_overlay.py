"""Tests for capture/selection_overlay.py."""

from unittest.mock import MagicMock, patch

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QGuiApplication, QImage, QKeyEvent, QMouseEvent, QPixmap, QScreen

from capture.screen_capture import CapturedMonitor
from capture.selection_overlay import OverlayManager, SelectionOverlay


def create_mock_monitor(width: int = 1920, height: int = 1080, dpr: float = 1.0) -> CapturedMonitor:
    """Helper to create an in-memory CapturedMonitor for headless testing."""
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.white)
    image = pixmap.toImage()
    screen = QGuiApplication.primaryScreen()

    return CapturedMonitor(
        name="MockDisplay",
        screen=screen,
        logical_geometry=QRect(0, 0, width, height),
        dpr=dpr,
        pixmap=pixmap,
        image=image,
    )


def test_tiny_selection_rejected(qtbot):
    """Verify selections < 8x8 physical pixels are ignored and never confirmed."""
    monitor = create_mock_monitor(1920, 1080, dpr=1.0)
    manager = OverlayManager()
    qtbot.addWidget(manager)

    overlay = SelectionOverlay(monitor, manager)
    qtbot.addWidget(overlay)

    confirmed_crops = []
    manager.crop_confirmed.connect(confirmed_crops.append)

    # Simulate mouse drag of 4x4 pixels
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(10, 10),
        QPoint(10, 10),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mousePressEvent(press_event)

    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPoint(14, 14),
        QPoint(14, 14),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseMoveEvent(move_event)

    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(14, 14),
        QPoint(14, 14),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseReleaseEvent(release_event)

    # Should not confirm because 4x4 < 8x8
    assert len(confirmed_crops) == 0
    assert overlay.selection_rect is None


def test_valid_selection_confirmed(qtbot):
    """Verify valid selections (>= 8x8 px) extract crop and emit confirmation."""
    monitor = create_mock_monitor(1920, 1080, dpr=1.0)
    manager = OverlayManager()
    qtbot.addWidget(manager)

    overlay = SelectionOverlay(monitor, manager)
    qtbot.addWidget(overlay)

    confirmed_crops = []
    manager.crop_confirmed.connect(confirmed_crops.append)

    # Simulate mouse drag of 100x80 pixels
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(10, 10),
        QPoint(10, 10),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mousePressEvent(press_event)

    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPoint(110, 90),
        QPoint(110, 90),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseMoveEvent(move_event)

    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(110, 90),
        QPoint(110, 90),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseReleaseEvent(release_event)

    assert len(confirmed_crops) == 1
    crop = confirmed_crops[0]
    assert crop.width() == 100
    assert crop.height() == 80


def test_esc_key_cancels(qtbot):
    """Verify Esc key triggers cancel and emits cancelled signal."""
    monitor = create_mock_monitor()
    manager = OverlayManager()
    qtbot.addWidget(manager)

    overlay = SelectionOverlay(monitor, manager)
    qtbot.addWidget(overlay)

    cancelled = []
    manager.cancelled.connect(lambda: cancelled.append(True))

    esc_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Escape,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.keyPressEvent(esc_event)

    assert len(cancelled) == 1


def test_right_click_cancels(qtbot):
    """Verify right-click immediately cancels the selection."""
    monitor = create_mock_monitor()
    manager = OverlayManager()
    qtbot.addWidget(manager)

    overlay = SelectionOverlay(monitor, manager)
    qtbot.addWidget(overlay)

    cancelled = []
    manager.cancelled.connect(lambda: cancelled.append(True))

    right_click = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(50, 50),
        QPoint(50, 50),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mousePressEvent(right_click)

    assert len(cancelled) == 1


def test_backspace_clears_selection(qtbot):
    """Verify Backspace key clears the current selection without cancelling."""
    monitor = create_mock_monitor()
    manager = OverlayManager()
    qtbot.addWidget(manager)

    overlay = SelectionOverlay(monitor, manager)
    qtbot.addWidget(overlay)

    # Set selection
    overlay.selection_rect = QRect(10, 10, 50, 50)

    backspace_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Backspace,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.keyPressEvent(backspace_event)

    assert overlay.selection_rect is None


def test_safety_timeout_cancels(qtbot):
    """Verify that the 60s inactivity safety timer triggers cancel."""
    manager = OverlayManager()
    qtbot.addWidget(manager)

    cancelled = []
    manager.cancelled.connect(lambda: cancelled.append(True))

    manager.safety_timer.timeout.emit()
    assert len(cancelled) == 1


def test_restore_foreground_hwnd_on_cancel(qtbot):
    """Verify saved foreground HWND is restored when selection is cancelled."""
    manager = OverlayManager()
    qtbot.addWidget(manager)
    manager.saved_foreground_hwnd = 98765

    with patch("core.win32.set_foreground_window") as mock_set_fg:
        manager.cancel()
        mock_set_fg.assert_called_once_with(98765)
