"""Peachy Cute Popup Window.

Implements the Day 4 visual identity and polite window behavior:
- White card with 16px radius, soft drop shadow, and pink accents
- Sparkle mascot vector integration
- Short / Detailed length chip
- Bouncing dots thinking animation (zero timer execution while hidden)
- Frameless, Qt.Tool, stay-on-top toggleable via Pin button (pinned by default)
- Polite focus: AskView accepts typing focus, AnswerView renders without stealing focus
- Minimizes to a floating pink pill and expands on click
- Header dragging with strict screen boundary clamping
"""

from __future__ import annotations

from enum import IntEnum
import logging
import math
from pathlib import Path
import sys
from typing import Optional

from PySide6.QtCore import (
    QEvent,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPixmap,
    QScreen,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from capture.geometry import clamp_popup_to_screen
from ui.theme import ThemeTokens, get_app_font, get_card_stylesheet, get_theme

logger = logging.getLogger(__name__)


def get_resource_path(relative_name: str) -> Path:
    """Resolve resource file supporting both source execution and PyInstaller frozen bundle."""
    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
        candidate = base_dir / "resources" / relative_name
        if candidate.exists():
            return candidate
        exe_dir = Path(sys.executable).resolve().parent
        candidate_exe = exe_dir / "resources" / relative_name
        if candidate_exe.exists():
            return candidate_exe
    return Path(__file__).resolve().parent.parent / "resources" / relative_name


RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
SPARKLE_SVG_PATH = get_resource_path("sparkle.svg")


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
    """Calculate popup position adjacent to selection rectangle, clamped inside screen."""
    pw, ph = popup_size.width(), popup_size.height()
    ag = available_geometry

    # 1. Try placing to the Right
    x_right = selection_rect.right() + margin
    if x_right + pw <= ag.right():
        y = max(ag.top(), min(selection_rect.top(), ag.bottom() - ph))
        cx, cy = clamp_popup_to_screen(x_right, y, pw, ph, ag.x(), ag.y(), ag.width(), ag.height())
        return QPoint(cx, cy)

    # 2. Try placing to the Left
    x_left = selection_rect.left() - margin - pw
    if x_left >= ag.left():
        y = max(ag.top(), min(selection_rect.top(), ag.bottom() - ph))
        cx, cy = clamp_popup_to_screen(x_left, y, pw, ph, ag.x(), ag.y(), ag.width(), ag.height())
        return QPoint(cx, cy)

    # 3. Try placing Below
    y_below = selection_rect.bottom() + margin
    if y_below + ph <= ag.bottom():
        x = max(ag.left(), min(selection_rect.left(), ag.right() - pw))
        cx, cy = clamp_popup_to_screen(x, y_below, pw, ph, ag.x(), ag.y(), ag.width(), ag.height())
        return QPoint(cx, cy)

    # 4. Try placing Above
    y_above = selection_rect.top() - margin - ph
    if y_above >= ag.top():
        x = max(ag.left(), min(selection_rect.left(), ag.right() - pw))
        cx, cy = clamp_popup_to_screen(x, y_above, pw, ph, ag.x(), ag.y(), ag.width(), ag.height())
        return QPoint(cx, cy)

    # 5. Fallback: Center
    fallback_x = max(ag.left(), min(selection_rect.center().x() - pw // 2, ag.right() - pw))
    fallback_y = max(ag.top(), min(selection_rect.center().y() - ph // 2, ag.bottom() - ph))
    cx, cy = clamp_popup_to_screen(fallback_x, fallback_y, pw, ph, ag.x(), ag.y(), ag.width(), ag.height())
    return QPoint(cx, cy)


class SparkleWidget(QWidget):
    """Renders the Peachy sparkle mascot SVG with DPI crispness."""

    def __init__(self, size: int = 20, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._renderer: Optional[QSvgRenderer] = None
        if SPARKLE_SVG_PATH.exists():
            self._renderer = QSvgRenderer(str(SPARKLE_SVG_PATH))

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._renderer and self._renderer.isValid():
            self._renderer.render(painter, self.rect())
        else:
            # Fallback procedural 4-point star if SVG is missing
            painter.setBrush(QColor("#F472B6"))
            painter.setPen(Qt.PenStyle.NoPen)
            w, h = self.width(), self.height()
            mx, my = w / 2, h / 2
            path = QPainter.Path()
            path.moveTo(mx, 1)
            path.quadTo(mx, my, w - 1, my)
            path.quadTo(mx, my, mx, h - 1)
            path.quadTo(mx, my, 1, my)
            path.quadTo(mx, my, mx, 1)
            painter.drawPath(path)


class BouncingDotsWidget(QWidget):
    """Three cute bouncing pink dots for the Thinking view.

    Guaranteed zero animation timer running when hidden.
    """

    def __init__(self, color: str = "#F472B6", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setFixedSize(64, 28)
        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 FPS
        self._timer.timeout.connect(self._on_tick)

    def _on_tick(self) -> None:
        self._phase += 0.18
        if self._phase >= 2 * math.pi:
            self._phase -= 2 * math.pi
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._timer.isActive():
            self._timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        if self._timer.isActive():
            self._timer.stop()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self.color)
        painter.setPen(Qt.PenStyle.NoPen)

        radius = 4.0
        spacing = 16.0
        center_x = self.width() / 2.0
        base_y = self.height() / 2.0

        for i in range(3):
            dot_x = center_x + (i - 1) * spacing
            offset = math.sin(self._phase + i * 0.9) * 5.0
            painter.drawEllipse(QPoint(int(dot_x), int(base_y + offset)), radius, radius)


class AskView(QWidget):
    """View 1: Thumbnail with dashed pink border, prompt input, and buttons."""

    send_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme = theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        # Thumbnail container with dashed pink border
        self.thumbnail_frame = QFrame()
        self.thumbnail_frame.setFixedHeight(120)
        self.thumbnail_frame.setStyleSheet(
            f"border: 2px dashed {theme.accent}; border-radius: 12px; background-color: {theme.surface};"
        )
        thumb_layout = QVBoxLayout(self.thumbnail_frame)
        thumb_layout.setContentsMargins(4, 4, 4, 4)

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_layout.addWidget(self.thumbnail_label)
        layout.addWidget(self.thumbnail_frame)

        # Question input field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask about this...")
        self.input_field.setFont(get_app_font(13))
        layout.addWidget(self.input_field)

        # Bottom row: Hint text + Cancel and Send buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(2, 0, 2, 0)

        self.hint_label = QLabel("Enter to send, Esc to cancel")
        self.hint_label.setFont(get_app_font(11))
        self.hint_label.setStyleSheet(f"color: {theme.muted};")
        bottom_layout.addWidget(self.hint_label)
        bottom_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("secondaryButton")
        self.cancel_btn.setFont(get_app_font(12))

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.setFont(get_app_font(12, QFont.Weight.DemiBold))
        self.send_btn.setDefault(True)

        bottom_layout.addWidget(self.cancel_btn)
        bottom_layout.addWidget(self.send_btn)
        layout.addLayout(bottom_layout)

        # Connections
        self.send_btn.clicked.connect(self._on_send)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)
        self.input_field.returnPressed.connect(self._on_send)

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self.thumbnail_label.clear()
            return
        scaled = pixmap.scaled(
            280,
            110,
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
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_requested.emit()
        else:
            super().keyPressEvent(event)


class ThinkingView(QWidget):
    """View 2: Cute bouncing pink dots with Cancel button."""

    cancel_requested = Signal()

    def __init__(self, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 28, 16, 20)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Bouncing dots animation
        self.dots = BouncingDotsWidget(color=theme.accent, parent=self)
        layout.addWidget(self.dots, alignment=Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("Thinking...")
        self.status_label.setFont(get_app_font(13, QFont.Weight.DemiBold))
        self.status_label.setStyleSheet(f"color: {theme.text};")
        layout.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("secondaryButton")
        self.cancel_btn.setFont(get_app_font(12))
        layout.addWidget(self.cancel_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.cancel_btn.clicked.connect(self.cancel_requested.emit)


class AnswerView(QWidget):
    """View 3: Rendered markdown answer, Copy with 1.5s toast, follow-up pill, and actions."""

    followup_requested = Signal(str)
    new_screenshot_requested = Signal()
    close_requested = Signal()

    def __init__(self, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme = theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # First-answer title header: "Here's the answer!"
        self.header_title = QLabel("Here's the answer!")
        self.header_title.setFont(get_app_font(13, QFont.Weight.DemiBold))
        self.header_title.setStyleSheet(f"color: {theme.accent}; margin-bottom: 2px;")
        layout.addWidget(self.header_title)

        # Question subtitle header
        self.question_header = QLabel()
        self.question_header.setWordWrap(True)
        self.question_header.setFont(get_app_font(11))
        self.question_header.setStyleSheet(f"color: {theme.muted}; margin-bottom: 4px;")
        layout.addWidget(self.question_header)

        # Top Action Bar: Copy button, New Screenshot, Done
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setObjectName("secondaryButton")
        self.copy_btn.setFont(get_app_font(11))
        self.copy_btn.setToolTip("Copy answer to clipboard")

        self.new_screen_btn = QPushButton("New Screenshot")
        self.new_screen_btn.setObjectName("secondaryButton")
        self.new_screen_btn.setFont(get_app_font(11))
        self.new_screen_btn.setToolTip("Box a new area and continue this chat")

        self.done_btn = QPushButton("Done")
        self.done_btn.setObjectName("secondaryButton")
        self.done_btn.setFont(get_app_font(11))
        self.done_btn.setToolTip("Close conversation (Esc)")

        top_bar.addWidget(self.copy_btn)
        top_bar.addStretch()
        top_bar.addWidget(self.new_screen_btn)
        top_bar.addWidget(self.done_btn)
        layout.addLayout(top_bar)

        # Markdown Answer Browser with customized scroll area
        self.browser = QTextBrowser()
        self.browser.setObjectName("answerBrowser")
        self.browser.setOpenExternalLinks(True)
        self.browser.setFont(get_app_font(13))
        self.browser.setMinimumHeight(140)
        self.browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.browser)

        # Follow-up Input Bar (Rounded Pill style)
        followup_layout = QHBoxLayout()
        followup_layout.setContentsMargins(0, 4, 0, 0)
        followup_layout.setSpacing(6)

        self.followup_input = QLineEdit()
        self.followup_input.setPlaceholderText("Ask a follow-up...")
        self.followup_input.setFont(get_app_font(12))

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.setFont(get_app_font(12, QFont.Weight.DemiBold))

        followup_layout.addWidget(self.followup_input)
        followup_layout.addWidget(self.send_btn)
        layout.addLayout(followup_layout)

        # Single-shot timer to reset Copy button text after 1.5 seconds
        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.timeout.connect(lambda: self.copy_btn.setText("Copy"))

        # Connections
        self.copy_btn.clicked.connect(self._on_copy)
        self.send_btn.clicked.connect(self._on_followup)
        self.followup_input.returnPressed.connect(self._on_followup)
        self.new_screen_btn.clicked.connect(self.new_screenshot_requested.emit)
        self.done_btn.clicked.connect(self.close_requested.emit)

    def set_answer(self, markdown_text: str, question: str = "", is_first_answer: bool = True) -> None:
        """Display answer with custom formatted markdown code blocks."""
        if is_first_answer:
            self.header_title.setText("Here's the answer!")
            self.header_title.show()
        else:
            self.header_title.hide()

        if question:
            self.question_header.setText(f"Q: {question}")
            self.question_header.show()
        else:
            self.question_header.hide()

        # Format monospace code blocks with soft pink background
        code_bg = self.theme.code_bg
        code_border = self.theme.border
        text_color = self.theme.text
        doc = self.browser.document()
        doc.setDefaultStyleSheet(f"""
            pre {{
                background-color: {code_bg};
                border: 1px solid {code_border};
                border-radius: 6px;
                padding: 8px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
                color: {text_color};
            }}
            code {{
                background-color: {code_bg};
                border-radius: 4px;
                padding: 2px 4px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
                color: {text_color};
            }}
            p {{ margin-bottom: 6px; }}
            ul, ol {{ margin-left: 16px; margin-bottom: 6px; }}
        """)
        self.browser.setMarkdown(markdown_text)

        self.copy_btn.setText("Copy")
        self.followup_input.clear()
        self.send_btn.setEnabled(True)
        self.followup_input.setEnabled(True)

    def _on_copy(self) -> None:
        text = self.browser.toPlainText()
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        self.copy_btn.setText("Copied!")
        self._copy_timer.start(1500)  # 1.5 s reset

    def _on_followup(self) -> None:
        q = self.followup_input.text().strip()
        if q:
            self.send_btn.setEnabled(False)
            self.followup_input.setEnabled(False)
            self.followup_requested.emit(q)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close_requested.emit()
        else:
            super().keyPressEvent(event)


class ErrorView(QWidget):
    """View 4: Friendly error explanation with Retry and Cancel buttons."""

    retry_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setFont(get_app_font(13))
        self.error_label.setStyleSheet(f"color: {theme.text};")
        layout.addWidget(self.error_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        self.retry_btn = QPushButton("Retry")
        self.retry_btn.setObjectName("primaryButton")
        self.retry_btn.setFont(get_app_font(12, QFont.Weight.DemiBold))

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("secondaryButton")
        self.cancel_btn.setFont(get_app_font(12))

        btn_layout.addStretch()
        btn_layout.addWidget(self.retry_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.retry_btn.clicked.connect(self.retry_requested.emit)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)


class MinimizedPillWidget(QWidget):
    """Floating compact pink pill shown when Peachy is minimized.

    Clicking expands back into full card. Draggable to any screen corner.
    """

    clicked = Signal()

    def __init__(self, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme = theme
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(110, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 12, 4)
        layout.setSpacing(6)

        self.sparkle = SparkleWidget(size=18, parent=self)
        layout.addWidget(self.sparkle)

        self.label = QLabel("peachy")
        self.label.setFont(get_app_font(13, QFont.Weight.DemiBold))
        self.label.setStyleSheet(f"color: {theme.accent};")
        layout.addWidget(self.label)
        layout.addStretch()

        self._drag_pos: Optional[QPoint] = None

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(self.theme.pill_bg))
        painter.setPen(QColor(self.theme.accent))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 17, 17)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            screen = QGuiApplication.screenAt(event.globalPosition().toPoint()) or QGuiApplication.primaryScreen()
            ag = screen.availableGeometry()
            cx, cy = clamp_popup_to_screen(new_pos.x(), new_pos.y(), self.width(), self.height(), ag.x(), ag.y(), ag.width(), ag.height())
            self.move(cx, cy)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            # If not dragged substantially, trigger expand
            self.clicked.emit()
            event.accept()


class PeachyPopup(QWidget):
    """The complete Peachy Cute Popup Window with aesthetic styling and polite behavior."""

    send_question = Signal(str)
    send_followup = Signal(str)
    retry_requested = Signal()
    new_screenshot_requested = Signal()
    cancelled = Signal()
    length_changed = Signal(str)  # "short" or "detailed"

    def __init__(self, pinned: bool = True, answer_length: str = "short", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._is_pinned = pinned
        self._answer_length = answer_length
        self._drag_pos: Optional[QPoint] = None
        self._is_first_answer = True

        # Resolve active theme
        self.theme = get_theme()

        self.setWindowTitle("Peachy")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | (Qt.WindowType.WindowStaysOnTopHint if self._is_pinned else Qt.WindowType.Widget)
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(380)

        # Outer layout providing margin for soft drop shadow
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(12, 12, 12, 12)

        # Main Card Container Frame
        self.card = QFrame(self)
        self.card.setObjectName("cardContainer")
        self.card.setStyleSheet(get_card_stylesheet(self.theme))

        # Soft card drop shadow
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(24)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(self.theme.shadow_color))
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(16, 14, 16, 16)
        card_layout.setSpacing(10)

        # Header bar
        self._build_header(card_layout)

        # Stacked views container
        self.stack = QStackedWidget(self.card)
        card_layout.addWidget(self.stack)

        # Build 4 view widgets
        self.ask_view = AskView(self.theme, self)
        self.thinking_view = ThinkingView(self.theme, self)
        self.answer_view = AnswerView(self.theme, self)
        self.error_view = ErrorView(self.theme, self)

        self.stack.addWidget(self.ask_view)       # Index 0
        self.stack.addWidget(self.thinking_view)  # Index 1
        self.stack.addWidget(self.answer_view)    # Index 2
        self.stack.addWidget(self.error_view)     # Index 3

        outer_layout.addWidget(self.card)

        # Floating minimized pill companion
        self.pill = MinimizedPillWidget(self.theme)
        self.pill.clicked.connect(self.expand_from_pill)

        self._connect_signals()

    def _build_header(self, parent_layout: QVBoxLayout) -> None:
        """Build header bar with mascot, title, subtitle, length chip, and actions."""
        self.header = QWidget(self.card)
        self.header.setCursor(Qt.CursorShape.SizeAllCursor)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 4)
        header_layout.setSpacing(8)

        # Mascot Sparkle
        self.sparkle_icon = SparkleWidget(size=22, parent=self.header)
        header_layout.addWidget(self.sparkle_icon)

        # Titles
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        self.title_label = QLabel("peachy")
        self.title_label.setObjectName("headerTitle")
        self.title_label.setFont(get_app_font(15, QFont.Weight.DemiBold))

        self.subtitle_label = QLabel("Screen assistant")
        self.subtitle_label.setObjectName("headerSubtitle")
        self.subtitle_label.setFont(get_app_font(11))

        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        # Length Chip ("Short" / "Detailed")
        self.chip_btn = QPushButton("Short" if self._answer_length == "short" else "Detailed")
        self.chip_btn.setObjectName("chipButton")
        self.chip_btn.setFont(get_app_font(11))
        self.chip_btn.setToolTip("Click to toggle Short / Detailed answers")
        self.chip_btn.clicked.connect(self._toggle_length_chip)
        header_layout.addWidget(self.chip_btn)

        # Action Buttons (Pin, Minimize, Close)
        self.pin_btn = QPushButton("📌" if self._is_pinned else "📍")
        self.pin_btn.setObjectName("iconButton")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(self._is_pinned)
        self.pin_btn.setToolTip("Unpin window" if self._is_pinned else "Pin to stay on top")
        self.pin_btn.clicked.connect(self._toggle_pin)
        header_layout.addWidget(self.pin_btn)

        self.minimize_btn = QPushButton("—")
        self.minimize_btn.setObjectName("iconButton")
        self.minimize_btn.setFont(get_app_font(12, QFont.Weight.Bold))
        self.minimize_btn.setToolTip("Minimize to floating pill")
        self.minimize_btn.clicked.connect(self.minimize_to_pill)
        header_layout.addWidget(self.minimize_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("iconButton")
        self.close_btn.setFont(get_app_font(12, QFont.Weight.Bold))
        self.close_btn.setToolTip("Close (Esc)")
        self.close_btn.clicked.connect(self.cancelled.emit)
        header_layout.addWidget(self.close_btn)

        parent_layout.addWidget(self.header)

    def _connect_signals(self) -> None:
        self.ask_view.send_requested.connect(self.send_question.emit)
        self.ask_view.cancel_requested.connect(self.cancelled.emit)

        self.thinking_view.cancel_requested.connect(self.cancelled.emit)

        self.answer_view.followup_requested.connect(self.send_followup.emit)
        self.answer_view.new_screenshot_requested.connect(self.new_screenshot_requested.emit)
        self.answer_view.close_requested.connect(self.cancelled.emit)

        self.error_view.retry_requested.connect(self.retry_requested.emit)
        self.error_view.cancel_requested.connect(self.cancelled.emit)

    def _toggle_length_chip(self) -> None:
        if self._answer_length == "short":
            self._answer_length = "detailed"
            self.chip_btn.setText("Detailed")
        else:
            self._answer_length = "short"
            self.chip_btn.setText("Short")
        self.length_changed.emit(self._answer_length)

    def _toggle_pin(self) -> None:
        self._is_pinned = not self._is_pinned
        self.pin_btn.setChecked(self._is_pinned)
        self.pin_btn.setText("📌" if self._is_pinned else "📍")
        self.pin_btn.setToolTip("Unpin window" if self._is_pinned else "Pin to stay on top")

        # Update Qt window flags seamlessly
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._is_pinned)
        self.show()

    def minimize_to_pill(self) -> None:
        """Collapse main card into the small floating pill companion."""
        card_pos = self.pos()
        self.hide()
        self.pill.move(card_pos.x() + 20, card_pos.y() + 20)
        self.pill.show()

    def expand_from_pill(self) -> None:
        """Expand floating pill back into the main card."""
        pill_pos = self.pill.pos()
        self.pill.hide()
        screen = QGuiApplication.screenAt(pill_pos) or QGuiApplication.primaryScreen()
        ag = screen.availableGeometry()
        cx, cy = clamp_popup_to_screen(pill_pos.x(), pill_pos.y(), self.width(), self.height(), ag.x(), ag.y(), ag.width(), ag.height())
        self.move(cx, cy)
        self.show()
        self.raise_()

    def show_ask(self, pixmap: QPixmap) -> None:
        """Display Ask view with focus enabled so the user can immediately type."""
        self._is_first_answer = True
        self.ask_view.set_thumbnail(pixmap)
        self.stack.setCurrentIndex(ViewIndex.ASK)

        # AskView needs focus
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.show()
        self.raise_()
        self.activateWindow()
        self.ask_view.focus_input()

    def show_thinking(self) -> None:
        """Display Thinking view."""
        self.stack.setCurrentIndex(ViewIndex.THINKING)
        self.show()
        self.raise_()

    def show_answer(self, markdown_text: str, question: str = "", is_first_answer: Optional[bool] = None) -> None:
        """Display Answer view without stealing focus from user's active window."""
        first = self._is_first_answer if is_first_answer is None else is_first_answer
        self.answer_view.set_answer(markdown_text, question=question, is_first_answer=first)
        self._is_first_answer = False
        self.stack.setCurrentIndex(ViewIndex.ANSWER)

        # Enforce polite focus: Answer view appears without stealing focus
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.show()
        self.raise_()

    def show_error(self, message: str) -> None:
        """Display Error view."""
        self.error_view.set_error(message)
        self.stack.setCurrentIndex(ViewIndex.ERROR)
        self.show()
        self.raise_()

    def position_next_to(self, selection_rect: QRect, screen: QScreen) -> None:
        """Position window adjacent to selection_rect within screen's work area."""
        pos = calculate_popup_position(
            selection_rect=selection_rect,
            popup_size=self.size(),
            available_geometry=screen.availableGeometry(),
        )
        self.move(pos)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            # Check if clicked inside header or top area for dragging
            header_rect = self.header.rect()
            header_rect.moveTopLeft(self.header.mapTo(self, QPoint(0, 0)))
            if header_rect.contains(event.position().toPoint()):
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            screen = QGuiApplication.screenAt(event.globalPosition().toPoint()) or QGuiApplication.primaryScreen()
            ag = screen.availableGeometry()
            cx, cy = clamp_popup_to_screen(new_pos.x(), new_pos.y(), self.width(), self.height(), ag.x(), ag.y(), ag.width(), ag.height())
            self.move(cx, cy)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)
