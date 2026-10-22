"""Unit tests for ui/peachy_popup.py covering aesthetics, polite focus, and views."""

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPixmap

from capture.geometry import clamp_popup_to_screen
from ui.peachy_popup import (
    BouncingDotsWidget,
    PeachyPopup,
    ViewIndex,
    calculate_popup_position,
)


def create_dummy_pixmap(width: int = 100, height: int = 100) -> QPixmap:
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(QColor(255, 180, 200))
    return QPixmap.fromImage(img)


def test_pure_function_clamp_popup_to_screen():
    """Verify popup coordinate clamping as a pure mathematical function."""
    # 1. Fits comfortably within bounds
    cx, cy = clamp_popup_to_screen(x=100, y=100, w=380, h=300, screen_x=0, screen_y=0, screen_w=1920, screen_h=1080)
    assert (cx, cy) == (100, 100)

    # 2. Exceeds right edge
    cx, cy = clamp_popup_to_screen(x=1800, y=100, w=380, h=300, screen_x=0, screen_y=0, screen_w=1920, screen_h=1080)
    assert cx == 1920 - 380
    assert cy == 100

    # 3. Exceeds bottom edge
    cx, cy = clamp_popup_to_screen(x=100, y=950, w=380, h=300, screen_x=0, screen_y=0, screen_w=1920, screen_h=1080)
    assert cx == 100
    assert cy == 1080 - 300

    # 4. Negative monitor origin (e.g. secondary monitor to the left)
    cx, cy = clamp_popup_to_screen(x=-1800, y=-50, w=380, h=300, screen_x=-1920, screen_y=-56, screen_w=1920, screen_h=1080)
    assert cx >= -1920
    assert cy >= -56


def test_calculate_popup_position_adjacent():
    """Verify popup positions to the right, or left if right is full."""
    sel = QRect(200, 200, 150, 100)
    psize = QSize(380, 280)
    avail = QRect(0, 0, 1920, 1080)

    # Placing to the right
    pos = calculate_popup_position(sel, psize, avail, margin=12)
    assert pos.x() == sel.right() + 12

    # If placed against right monitor boundary, falls back to left
    sel_edge = QRect(1700, 200, 150, 100)
    pos_edge = calculate_popup_position(sel_edge, psize, avail, margin=12)
    assert pos_edge.x() == sel_edge.left() - 12 - psize.width()


def test_popup_frameless_and_pin_toggle(qtbot):
    """Verify window flags: Frameless, Tool, and Pin toggle StaysOnTopHint."""
    popup = PeachyPopup(pinned=True)
    qtbot.addWidget(popup)

    # Pinned by default
    flags = popup.windowFlags()
    assert bool(flags & Qt.WindowType.FramelessWindowHint)
    assert bool(flags & Qt.WindowType.Tool)
    assert bool(flags & Qt.WindowType.WindowStaysOnTopHint)
    assert popup.pin_btn.isChecked()

    # Toggle Pin OFF
    popup._toggle_pin()
    assert not bool(popup.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    assert not popup.pin_btn.isChecked()

    # Toggle Pin ON
    popup._toggle_pin()
    assert bool(popup.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    assert popup.pin_btn.isChecked()


def test_view_switching_lifecycle(qtbot):
    """Verify views switch correctly between Ask, Thinking, Answer, and Error."""
    popup = PeachyPopup()
    qtbot.addWidget(popup)

    # 1. Ask View
    pix = create_dummy_pixmap(120, 60)
    popup.show_ask(pix)
    assert popup.stack.currentIndex() == ViewIndex.ASK
    qtbot.waitUntil(lambda: popup.ask_view.input_field.hasFocus(), timeout=1000)

    # 2. Thinking View
    popup.show_thinking()
    assert popup.stack.currentIndex() == ViewIndex.THINKING
    assert popup.thinking_view.dots.isVisible()

    # 3. Answer View
    popup.show_answer("# Result\nThis is **bold** text.", question="What is this?")
    assert popup.stack.currentIndex() == ViewIndex.ANSWER
    assert "Result" in popup.answer_view.browser.toPlainText()
    assert "bold" in popup.answer_view.browser.toPlainText()
    assert popup.answer_view.header_title.text() == "Here's the answer!"

    # 4. Error View
    popup.show_error("Network connection failed.")
    assert popup.stack.currentIndex() == ViewIndex.ERROR
    assert "Network connection failed." in popup.error_view.error_label.text()


def test_bouncing_dots_timer_strictly_stopped_when_hidden(qtbot):
    """Rule: No animation timers running while hidden."""
    dots = BouncingDotsWidget()
    qtbot.addWidget(dots)

    assert not dots._timer.isActive()

    # Showing widget activates timer
    dots.show()
    assert dots._timer.isActive()

    # Hiding widget stops timer immediately
    dots.hide()
    assert not dots._timer.isActive()


def test_copy_button_clipboard_and_timed_toast(qtbot):
    """Verify Copy button puts text on clipboard and resets 'Copied!' text."""
    popup = PeachyPopup()
    qtbot.addWidget(popup)

    answer_text = "Python is awesome\n```python\nprint(42)\n```"
    popup.show_answer(answer_text)

    # Click Copy
    popup.answer_view._on_copy()

    # Verify clipboard contents
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    assert "Python is awesome" in clipboard.text()
    assert popup.answer_view.copy_btn.text() == "Copied!"

    # After timer fires, reverts to "Copy"
    popup.answer_view._copy_timer.timeout.emit()
    assert popup.answer_view.copy_btn.text() == "Copy"


def test_minimize_and_expand_pill(qtbot):
    """Verify minimizing collapses to floating pill and clicking pill restores card."""
    popup = PeachyPopup()
    qtbot.addWidget(popup)
    qtbot.addWidget(popup.pill)

    popup.show()
    assert popup.isVisible()
    assert not popup.pill.isVisible()

    # Minimize
    popup.minimize_to_pill()
    assert not popup.isVisible()
    assert popup.pill.isVisible()

    # Click pill to expand
    popup.expand_from_pill()
    assert popup.isVisible()
    assert not popup.pill.isVisible()


def test_length_chip_toggle(qtbot):
    """Verify Short / Detailed length chip toggles and emits signal."""
    popup = PeachyPopup(answer_length="short")
    qtbot.addWidget(popup)

    assert popup.chip_btn.text() == "Short"

    emitted_lengths = []
    popup.length_changed.connect(emitted_lengths.append)

    # Toggle to Detailed
    popup._toggle_length_chip()
    assert popup.chip_btn.text() == "Detailed"
    assert emitted_lengths[-1] == "detailed"

    # Toggle back to Short
    popup._toggle_length_chip()
    assert popup.chip_btn.text() == "Short"
    assert emitted_lengths[-1] == "short"


def test_polite_focus_answer_view_does_not_steal_focus(qtbot):
    """Verify AnswerView sets WA_ShowWithoutActivating attribute."""
    popup = PeachyPopup()
    qtbot.addWidget(popup)

    popup.show_answer("Polite answer text")
    assert popup.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_set_answer_length(qtbot):
    """Verify set_answer_length sets internal mode and chip text."""
    popup = PeachyPopup(answer_length="short")
    qtbot.addWidget(popup)

    popup.set_answer_length("detailed")
    assert popup._answer_length == "detailed"
    assert popup.chip_btn.text() == "Detailed"

    popup.set_answer_length("short")
    assert popup._answer_length == "short"
    assert popup.chip_btn.text() == "Short"
