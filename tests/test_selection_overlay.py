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
    """Verify selections < 8x8 physical pixels are ignored in rectangle mode."""
    monitor = create_mock_monitor(1920, 1080, dpr=1.0)
    manager = OverlayManager()
    manager.set_mode("rectangle")
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
    """Verify valid selections (>= 8x8 px) in rectangle mode extract crop and emit confirmation."""
    monitor = create_mock_monitor(1920, 1080, dpr=1.0)
    manager = OverlayManager()
    manager.set_mode("rectangle")
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


def test_default_mode_is_freehand_and_tab_toggles(qtbot):
    """Verify overlay starts in Freehand mode and Tab toggles between Freehand and Rectangle."""
    monitor = create_mock_monitor()
    manager = OverlayManager()
    qtbot.addWidget(manager)

    assert manager.mode == "freehand"

    overlay = SelectionOverlay(monitor, manager)
    qtbot.addWidget(overlay)

    tab_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    overlay.keyPressEvent(tab_event)
    assert manager.mode == "rectangle"

    overlay.keyPressEvent(tab_event)
    assert manager.mode == "freehand"


def test_freehand_single_click_ignored(qtbot):
    """Verify a single click without moving is degenerate and never confirms."""
    monitor = create_mock_monitor()
    manager = OverlayManager()
    qtbot.addWidget(manager)

    overlay = SelectionOverlay(monitor, manager)
    qtbot.addWidget(overlay)

    confirmed_crops = []
    manager.crop_confirmed.connect(confirmed_crops.append)

    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(50, 50),
        QPoint(50, 50),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mousePressEvent(press)

    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(50, 50),
        QPoint(50, 50),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseReleaseEvent(release)

    assert len(confirmed_crops) == 0
    assert len(overlay.completed_strokes_physical) == 0


def test_freehand_straight_line_ignored(qtbot):
    """Verify drawing a straight line is ignored as degenerate input."""
    monitor = create_mock_monitor()
    manager = OverlayManager()
    qtbot.addWidget(manager)

    overlay = SelectionOverlay(monitor, manager)
    qtbot.addWidget(overlay)

    confirmed_crops = []
    manager.crop_confirmed.connect(confirmed_crops.append)

    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(10, 10),
        QPoint(10, 10),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mousePressEvent(press)

    # Move along a straight diagonal
    for x in (20, 30, 40, 50, 60):
        move = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPoint(x, x),
            QPoint(x, x),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mouseMoveEvent(move)

    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(60, 60),
        QPoint(60, 60),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseReleaseEvent(release)

    # Straight line must be ignored
    assert len(confirmed_crops) == 0


def test_freehand_valid_stroke_confirmed(qtbot):
    """Verify drawing a valid closed loop confirms selection and emits cropped image."""
    monitor = create_mock_monitor(1920, 1080, dpr=1.0)
    manager = OverlayManager()
    qtbot.addWidget(manager)

    overlay = SelectionOverlay(monitor, manager)
    qtbot.addWidget(overlay)

    confirmed_crops = []
    manager.crop_confirmed.connect(confirmed_crops.append)

    # Draw a 50x50 loop: (10, 10) -> (60, 10) -> (60, 60) -> (10, 60) -> (10, 12)
    path_points = [
        (10, 10),
        (25, 10),
        (40, 10),
        (60, 10),
        (60, 30),
        (60, 60),
        (35, 60),
        (10, 60),
        (10, 35),
        (10, 12),
    ]

    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPoint(path_points[0][0], path_points[0][1]),
        QPoint(path_points[0][0], path_points[0][1]),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mousePressEvent(press)

    for pt in path_points[1:]:
        move = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPoint(pt[0], pt[1]),
            QPoint(pt[0], pt[1]),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        overlay.mouseMoveEvent(move)

    release = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(path_points[-1][0], path_points[-1][1]),
        QPoint(path_points[-1][0], path_points[-1][1]),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    overlay.mouseReleaseEvent(release)

    assert len(confirmed_crops) == 1
    crop = confirmed_crops[0]
    assert crop.width() == 50
    assert crop.height() == 50


def test_freehand_shift_multi_stroke_union_and_enter(qtbot):
    """Verify Shift held keeps selection open for next stroke, and Enter confirms union."""
    monitor = create_mock_monitor(1920, 1080, dpr=1.0)
    manager = OverlayManager()
    qtbot.addWidget(manager)

    overlay = SelectionOverlay(monitor, manager)
    qtbot.addWidget(overlay)

    confirmed_crops = []
    manager.crop_confirmed.connect(confirmed_crops.append)

    # Stroke 1: 10..30, 10..30
    s1 = [(10, 10), (30, 10), (30, 30), (10, 30), (10, 12)]
    overlay.mousePressEvent(
        QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPoint(10, 10), QPoint(10, 10),
                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)
    )
    for pt in s1[1:]:
        overlay.mouseMoveEvent(
            QMouseEvent(QMouseEvent.Type.MouseMove, QPoint(pt[0], pt[1]), QPoint(pt[0], pt[1]),
                        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)
        )
    # Release WITH Shift held
    overlay.mouseReleaseEvent(
        QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPoint(10, 12), QPoint(10, 12),
                    Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.ShiftModifier)
    )

    # Selection must remain OPEN, no crop confirmed yet
    assert len(confirmed_crops) == 0
    assert len(overlay.completed_strokes_physical) == 1

    # Stroke 2: 50..80, 50..80
    s2 = [(50, 50), (80, 50), (80, 80), (50, 80), (50, 52)]
    overlay.mousePressEvent(
        QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPoint(50, 50), QPoint(50, 50),
                    Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)
    )
    for pt in s2[1:]:
        overlay.mouseMoveEvent(
            QMouseEvent(QMouseEvent.Type.MouseMove, QPoint(pt[0], pt[1]), QPoint(pt[0], pt[1]),
                        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)
        )
    overlay.mouseReleaseEvent(
        QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPoint(50, 52), QPoint(50, 52),
                    Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.ShiftModifier)
    )

    assert len(confirmed_crops) == 0
    assert len(overlay.completed_strokes_physical) == 2

    # Press Enter to confirm union
    enter_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    overlay.keyPressEvent(enter_event)

    assert len(confirmed_crops) == 1
    crop = confirmed_crops[0]
    # Union bbox: x: 10..80 (w=70), y: 10..80 (h=70)
    assert crop.width() == 70
    assert crop.height() == 70


def test_freehand_backspace_clears_strokes(qtbot):
    """Verify Backspace key clears all completed and in-progress freehand strokes."""
    monitor = create_mock_monitor()
    manager = OverlayManager()
    qtbot.addWidget(manager)

    overlay = SelectionOverlay(monitor, manager)
    qtbot.addWidget(overlay)

    # Add a completed stroke
    overlay.completed_strokes_physical.append([(10, 10), (30, 10), (30, 30), (10, 30), (10, 10)])
    overlay.completed_strokes_logical.append([QPoint(10, 10), QPoint(30, 10), QPoint(30, 30)])

    backspace = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Backspace, Qt.KeyboardModifier.NoModifier)
    overlay.keyPressEvent(backspace)

    assert len(overlay.completed_strokes_physical) == 0
    assert len(overlay.completed_strokes_logical) == 0


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
