"""Peachy Popup Window with plain styling.

Switches between Ask, Thinking, Answer, and Error views using QStackedWidget.
Positions itself next to the user's screen selection while remaining strictly
within the target monitor's available desktop area.
"""

from __future__ import annotations

from enum import IntEnum
import logging
from typing import Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QImage, QKeyEvent, QPixmap, QScreen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class ViewIndex(IntEnum):
    ASK = 0
    THINKING = 1
    ANSWER = 2
    ERROR = 3


def calculate_popup_position(
    selection_rect: QRect,
    popup_size: QSize,
    available_geometry: QRect,
    margin: int = 12,
) -> QPoint:
    """Calculate popup position adjacent to the selection rectangle.

    Tries Right -> Left -> Below -> Above, always clamping strictly inside
    the monitor's available desktop boundaries.
    """
    pw, ph = popup_size.width(), popup_size.height()
    ag = available_geometry

    # 1. Try placing to the Right
    x_right = selection_rect.right() + margin
    if x_right + pw <= ag.right():
        y = max(ag.top(), min(selection_rect.top(), ag.bottom() - ph))
        return QPoint(x_right, y)

    # 2. Try placing to the Left
    x_left = selection_rect.left() - margin - pw
    if x_left >= ag.left():
        y = max(ag.top(), min(selection_rect.top(), ag.bottom() - ph))
        return QPoint(x_left, y)

    # 3. Try placing Below
    y_below = selection_rect.bottom() + margin
    if y_below + ph <= ag.bottom():
        x = max(ag.left(), min(selection_rect.left(), ag.right() - pw))
        return QPoint(x, y_below)

    # 4. Try placing Above
    y_above = selection_rect.top() - margin - ph
    if y_above >= ag.top():
        x = max(ag.left(), min(selection_rect.left(), ag.right() - pw))
        return QPoint(x, y_above)

    # 5. Fallback: Center or strictly clamp within screen
    fallback_x = max(ag.left(), min(selection_rect.center().x() - pw // 2, ag.right() - pw))
    fallback_y = max(ag.top(), min(selection_rect.center().y() - ph // 2, ag.bottom() - ph))
    return QPoint(fallback_x, fallback_y)


class AskView(QWidget):
    """View 1: Displays crop thumbnail, question text field, Send/Cancel buttons, and Esc hint."""

    send_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setFixedHeight(120)
        self.thumbnail_label.setStyleSheet("border: 1px solid #ccc; background: #222;")
        layout.addWidget(self.thumbnail_label)

        # Question input field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask a question about this screenshot (or leave empty to explain)...")
        layout.addWidget(self.input_field)

        # Hint label
        self.hint_label = QLabel("Press Enter to send • Esc to cancel")
        self.hint_label.setStyleSheet("color: #777; font-size: 11px;")
        layout.addWidget(self.hint_label)

        # Buttons
        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        self.send_btn = QPushButton("Send")
        self.send_btn.setDefault(True)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.send_btn)
        layout.addLayout(btn_layout)

        # Connections
        self.send_btn.clicked.connect(self._on_send)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        self.input_field.returnPressed.connect(self._on_send)

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        """Set and scale crop thumbnail for preview."""
        if pixmap.isNull():
            self.thumbnail_label.clear()
            return
        scaled = pixmap.scaled(
            240,
            120,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.thumbnail_label.setPixmap(scaled)

    def focus_input(self) -> None:
        self.input_field.setFocus()
        self.input_field.selectAll()

    def clear(self) -> None:
        self.input_field.clear()
        self.thumbnail_label.clear()

    def _on_send(self) -> None:
        self.send_requested.emit(self.input_field.text().strip())

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_send()
        elif event.key() == Qt.Key.Key_Escape:
            self.cancel_requested.emit()
        else:
            super().keyPressEvent(event)


class ThinkingView(QWidget):
    """View 2: Displays 'Thinking...' status with a Cancel button."""

    cancel_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(16)

        self.label = QLabel("Thinking...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.label.font()
        font.setPointSize(12)
        font.setBold(True)
        self.label.setFont(font)
        layout.addWidget(self.label)

        btn_layout = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancel")
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.cancel_btn.clicked.connect(self.cancel_requested.emit)


class AnswerView(QWidget):
    """View 3: Displays question header, rendered markdown answer, copy, follow-up, and actions."""

    followup_requested = Signal(str)
    new_screenshot_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Question header
        self.question_header = QLabel()
        self.question_header.setWordWrap(True)
        font = self.question_header.font()
        font.setBold(True)
        font.setPointSize(10)
        self.question_header.setFont(font)
        self.question_header.setStyleSheet("color: #333; margin-bottom: 2px;")
        layout.addWidget(self.question_header)

        # Top Action Bar
        top_bar = QHBoxLayout()
        self.copy_btn = QPushButton("Copy")
        self.new_screen_btn = QPushButton("New Screenshot")
        self.done_btn = QPushButton("Done")

        top_bar.addWidget(self.copy_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.new_screen_btn)
        top_bar.addWidget(self.done_btn)
        layout.addLayout(top_bar)

        # Markdown Answer Browser
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setMinimumHeight(180)
        layout.addWidget(self.browser)

        # Follow-up Bar
        followup_layout = QHBoxLayout()
        self.followup_input = QLineEdit()
        self.followup_input.setPlaceholderText("Ask a follow-up...")
        self.send_btn = QPushButton("Send")

        followup_layout.addWidget(self.followup_input)
        followup_layout.addWidget(self.send_btn)
        layout.addLayout(followup_layout)

        # Connections
        self.copy_btn.clicked.connect(self._on_copy)
        self.send_btn.clicked.connect(self._on_followup)
        self.followup_input.returnPressed.connect(self._on_followup)
        self.new_screen_btn.clicked.connect(self.new_screenshot_requested.emit)
        self.done_btn.clicked.connect(self.close_requested.emit)

    def set_answer(self, markdown_text: str, question: str = "") -> None:
        if question:
            self.question_header.setText(f"Q: {question}")
            self.question_header.show()
        else:
            self.question_header.hide()

        self.browser.setMarkdown(markdown_text)
        self.copy_btn.setText("Copy")
        self.followup_input.clear()
        self.send_btn.setEnabled(True)
        self.followup_input.setEnabled(True)
        self.followup_input.setFocus()

    def _on_copy(self) -> None:
        text = self.browser.toPlainText()
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        self.copy_btn.setText("Copied!")

    def _on_followup(self) -> None:
        q = self.followup_input.text().strip()
        if q:
            self.send_btn.setEnabled(False)
            self.followup_input.setEnabled(False)
            self.followup_requested.emit(q)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.followup_input.hasFocus():
                self._on_followup()
        elif event.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
        else:
            super().keyPressEvent(event)


class ErrorView(QWidget):
    """View 4: Displays friendly error message with Retry and Cancel buttons."""

    retry_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(12)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.error_label)

        btn_layout = QHBoxLayout()
        self.retry_btn = QPushButton("Retry")
        self.cancel_btn = QPushButton("Cancel")

        btn_layout.addStretch()
        btn_layout.addWidget(self.retry_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.retry_btn.clicked.connect(self.retry_requested.emit)
        self.cancel_btn.clicked.connect(self.close_requested.emit)

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)


class PeachyPopup(QWidget):
    """Single unified popup window for Peachy containing Ask, Thinking, Answer, and Error views."""

    send_question = Signal(str)
    send_followup = Signal(str)
    retry_requested = Signal()
    new_screenshot_requested = Signal()
    cancelled = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Peachy")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setMinimumSize(380, 280)
        self.resize(420, 320)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget(self)
        main_layout.addWidget(self.stack)

        # Views
        self.ask_view = AskView(self)
        self.thinking_view = ThinkingView(self)
        self.answer_view = AnswerView(self)
        self.error_view = ErrorView(self)

        self.stack.addWidget(self.ask_view)       # Index 0
        self.stack.addWidget(self.thinking_view)  # Index 1
        self.stack.addWidget(self.answer_view)    # Index 2
        self.stack.addWidget(self.error_view)     # Index 3

        self._connect_view_signals()

    def _connect_view_signals(self) -> None:
        self.ask_view.send_requested.connect(self.send_question.emit)
        self.ask_view.cancel_requested.connect(self.cancelled.emit)

        self.thinking_view.cancel_requested.connect(self.cancelled.emit)

        self.answer_view.followup_requested.connect(self.send_followup.emit)
        self.answer_view.new_screenshot_requested.connect(self.new_screenshot_requested.emit)
        self.answer_view.close_requested.connect(self.cancelled.emit)

        self.error_view.retry_requested.connect(self.retry_requested.emit)
        self.error_view.close_requested.connect(self.cancelled.emit)

    def show_ask(self, pixmap: QPixmap) -> None:
        """Switch to Ask view with the provided crop pixmap."""
        self.ask_view.set_thumbnail(pixmap)
        self.stack.setCurrentIndex(ViewIndex.ASK)
        self.show()
        self.raise_()
        self.activateWindow()
        self.ask_view.focus_input()

    def show_thinking(self) -> None:
        """Switch to Thinking view."""
        self.stack.setCurrentIndex(ViewIndex.THINKING)
        self.show()
        self.raise_()

    def show_answer(self, markdown_text: str, question: str = "") -> None:
        """Switch to Answer view with the markdown response and question header."""
        self.answer_view.set_answer(markdown_text, question=question)
        self.stack.setCurrentIndex(ViewIndex.ANSWER)
        self.show()
        self.raise_()
        self.activateWindow()

    def show_error(self, message: str) -> None:
        """Switch to Error view with friendly message."""
        self.error_view.set_error(message)
        self.stack.setCurrentIndex(ViewIndex.ERROR)
        self.show()
        self.raise_()
        self.activateWindow()

    def position_next_to(self, selection_rect: QRect, screen: QScreen) -> None:
        """Position window adjacent to selection_rect within screen's available area."""
        pos = calculate_popup_position(
            selection_rect=selection_rect,
            popup_size=self.size(),
            available_geometry=screen.availableGeometry(),
        )
        self.move(pos)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)
