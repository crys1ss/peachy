"""Peachy Cute Popup Window.

Implements the Midnight visual identity and polite window behavior:
- Midnight canvas (#0B0B10) with surface card (#171720) and border (#292735)
- Brand orb mark vector integration with peach highlight
- Short / Detailed length chip (clean text + SVG icon, zero emoji)
- Custom vector SVG icons on a 20 px grid (1.5 px stroke)
- Bouncing dots thinking animation (zero timer execution while hidden)
- Frameless, Qt.Tool, stay-on-top toggleable via Pin button (pinned by default)
- Polite focus: AskView accepts typing focus, AnswerView renders without stealing focus
- Minimizes to a floating brand orb pill and expands on click
- Header dragging with strict screen boundary clamping
- Pygments syntax-highlighted code rendering with Cascadia Code / Consolas
- Sound effect triggers via SoundManager
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
    QCloseEvent,
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
from config.settings import Settings, load_settings
from core.win32 import get_client_area_animation_enabled
from ui.components.brand_orb import BrandOrb
from ui.components.code_highlighter import render_markdown_html
from ui.components.icons import get_svg_icon, get_svg_pixmap
from ui.components.toast import Toast
from ui.sound import get_sound_manager
from ui.theme import ThemeTokens, get_app_font, get_card_stylesheet, get_code_font, get_theme

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


def should_animate(settings: Optional[Settings] = None) -> bool:
    """Return True if UI animations should run, False if motion reduction is requested."""
    if settings is not None and getattr(settings, "reduce_motion", False):
        return False
    return get_client_area_animation_enabled()


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


class SparkleWidget(BrandOrb):
    """Mascot orb widget maintaining backward-compatibility with SparkleWidget callers."""

    def __init__(self, size: int = 20, parent: Optional[QWidget] = None):
        super().__init__(size=size, parent=parent)


class BouncingDotsWidget(QWidget):
    """Three cute bouncing pink dots for the Thinking view.

    Guaranteed zero animation timer running when hidden.
    """

    def __init__(self, color: str = "#FF6BCE", parent: Optional[QWidget] = None):
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
    """View 1: Thumbnail with border, prompt input, and buttons (zero emoji)."""

    send_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme = theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        # Thumbnail container with border
        self.thumbnail_frame = QFrame()
        self.thumbnail_frame.setFixedHeight(120)
        self.thumbnail_frame.setStyleSheet(
            f"border: 1.5px dashed {theme.border}; border-radius: 12px; background-color: {theme.secondary};"
        )
        thumb_layout = QVBoxLayout(self.thumbnail_frame)
        thumb_layout.setContentsMargins(4, 4, 4, 4)

        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_layout.addWidget(self.thumbnail_label)
        layout.addWidget(self.thumbnail_frame)

        # Question input field
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask a question, or pick an action below...")
        self.input_field.setFont(get_app_font(13))
        layout.addWidget(self.input_field)

        # Quick Action Preset Chips row (solid flat colors, zero emoji)
        chips_layout = QHBoxLayout()
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(5)

        self.solve_chip = QPushButton("Solve")
        self.solve_chip.setObjectName("presetChip")
        self.solve_chip.setIcon(get_svg_icon("solve", color=theme.text_secondary, size=14))
        self.solve_chip.setToolTip("Solve multiple-choice or direct problem")
        self.solve_chip.clicked.connect(lambda: self._on_preset("Solve this question or problem. State the correct answer or option first, then explain concisely."))

        self.fix_code_chip = QPushButton("Fix Code")
        self.fix_code_chip.setObjectName("presetChip")
        self.fix_code_chip.setIcon(get_svg_icon("fix_code", color=theme.text_secondary, size=14))
        self.fix_code_chip.setToolTip("Identify bug/error and provide corrected code")
        self.fix_code_chip.clicked.connect(lambda: self._on_preset("Identify the bug or error in this code. Provide the root cause and the exact corrected code."))

        self.translate_chip = QPushButton("Translate")
        self.translate_chip.setObjectName("presetChip")
        self.translate_chip.setIcon(get_svg_icon("translate", color=theme.text_secondary, size=14))
        self.translate_chip.setToolTip("Translate visible text to clear English")
        self.translate_chip.clicked.connect(lambda: self._on_preset("Translate all text in this image into clear, fluent English."))

        self.summarize_chip = QPushButton("Summarize")
        self.summarize_chip.setObjectName("presetChip")
        self.summarize_chip.setIcon(get_svg_icon("summarize", color=theme.text_secondary, size=14))
        self.summarize_chip.setToolTip("Summarize key takeaways in bullet points")
        self.summarize_chip.clicked.connect(lambda: self._on_preset("Summarize the key information and takeaways in this image into concise bullet points."))

        self.copy_text_chip = QPushButton("Copy Text")
        self.copy_text_chip.setObjectName("presetChip")
        self.copy_text_chip.setIcon(get_svg_icon("copy_text", color=theme.text_secondary, size=14))
        self.copy_text_chip.setToolTip("Extract all text and copy to clipboard")
        self.copy_text_chip.clicked.connect(lambda: self.send_requested.emit("Extract all visible text in this image verbatim. Do not add preamble, explanations, or commentary. Output raw text only."))

        chips_layout.addWidget(self.solve_chip)
        chips_layout.addWidget(self.fix_code_chip)
        chips_layout.addWidget(self.translate_chip)
        chips_layout.addWidget(self.summarize_chip)
        chips_layout.addWidget(self.copy_text_chip)
        layout.addLayout(chips_layout)

        # Bottom row: Hint text + Cancel and Send buttons
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(2, 0, 2, 0)

        self.hint_label = QLabel("Enter to send, Esc to cancel")
        self.hint_label.setFont(get_app_font(11))
        self.hint_label.setStyleSheet(f"color: {theme.text_secondary};")
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

    def _on_preset(self, preset_prompt: str) -> None:
        """Combine user input with selected preset prompt."""
        user_text = self.input_field.text().strip()
        if user_text:
            combined = f"{user_text}\n\n{preset_prompt}"
        else:
            combined = preset_prompt
        self.send_requested.emit(combined)

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
        self.dots = BouncingDotsWidget(color=theme.pink, parent=self)
        layout.addWidget(self.dots, alignment=Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("Thinking...")
        self.status_label.setFont(get_app_font(13, QFont.Weight.DemiBold))
        self.status_label.setStyleSheet(f"color: {theme.text_secondary};")
        layout.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Cancel button
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("secondaryButton")
        self.cancel_btn.setFont(get_app_font(12))
        layout.addWidget(self.cancel_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.cancel_btn.clicked.connect(self.cancel_requested.emit)


class AnswerView(QWidget):
    """View 3: Rendered markdown answer with Pygments code highlighting, vector icons, and actions."""

    followup_requested = Signal(str)
    new_screenshot_requested = Signal()
    close_requested = Signal()
    opt_in_choice = Signal(bool)

    def __init__(self, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme = theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # First-answer title header
        self.header_title = QLabel("Answer")
        self.header_title.setFont(get_app_font(13, QFont.Weight.DemiBold))
        self.header_title.setStyleSheet(f"color: {theme.pink}; margin-bottom: 2px;")
        layout.addWidget(self.header_title)

        # Question subtitle header
        self.question_header = QLabel()
        self.question_header.setWordWrap(True)
        self.question_header.setFont(get_app_font(11))
        self.question_header.setStyleSheet(f"color: {theme.text_secondary}; margin-bottom: 4px;")
        layout.addWidget(self.question_header)

        # Top Action Bar: Copy button, New Screenshot, Done (vector SVG icons, zero emoji)
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)

        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setIcon(get_svg_icon("copy", color=theme.text_secondary, size=14))
        self.copy_btn.setObjectName("secondaryButton")
        self.copy_btn.setFont(get_app_font(11))
        self.copy_btn.setToolTip("Copy answer to clipboard")

        self.new_screen_btn = QPushButton("New Screenshot")
        self.new_screen_btn.setIcon(get_svg_icon("crop", color=theme.text_secondary, size=14))
        self.new_screen_btn.setObjectName("secondaryButton")
        self.new_screen_btn.setFont(get_app_font(11))
        self.new_screen_btn.setToolTip("Box a new area and continue this chat")

        self.done_btn = QPushButton("Done")
        self.done_btn.setIcon(get_svg_icon("check", color=theme.text_secondary, size=14))
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

        # Toast notification component
        self.toast = Toast(parent=self)

        # Small note banner for history / multi-turn context
        self.note_label = QLabel("Earlier screenshots are not re-sent.")
        self.note_label.setFont(get_app_font(11))
        self.note_label.setStyleSheet(f"color: {theme.text_secondary}; font-style: italic; margin-top: 2px;")
        self.note_label.hide()
        layout.addWidget(self.note_label)

        # One-time Opt-In Banner for saving chat history
        self.opt_in_banner = QFrame()
        self.opt_in_banner.setStyleSheet(f"""
            QFrame {{
                background-color: {theme.secondary};
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 6px;
            }}
        """)
        opt_layout = QVBoxLayout(self.opt_in_banner)
        opt_layout.setContentsMargins(8, 6, 8, 6)
        opt_layout.setSpacing(6)

        opt_msg = QLabel("Save your chats on this PC so you can reopen them later? You can turn this off any time.")
        opt_msg.setWordWrap(True)
        opt_msg.setFont(get_app_font(11))
        opt_msg.setStyleSheet(f"color: {theme.text};")
        opt_layout.addWidget(opt_msg)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)
        btn_row.addStretch()

        self.opt_not_now_btn = QPushButton("Not now")
        self.opt_not_now_btn.setObjectName("secondaryButton")
        self.opt_not_now_btn.setFont(get_app_font(11))
        self.opt_not_now_btn.clicked.connect(lambda: self._on_opt_in_clicked(False))

        self.opt_save_btn = QPushButton("Save")
        self.opt_save_btn.setObjectName("primaryButton")
        self.opt_save_btn.setFont(get_app_font(11, QFont.Weight.DemiBold))
        self.opt_save_btn.clicked.connect(lambda: self._on_opt_in_clicked(True))

        btn_row.addWidget(self.opt_not_now_btn)
        btn_row.addWidget(self.opt_save_btn)
        opt_layout.addLayout(btn_row)

        self.opt_in_banner.hide()
        layout.addWidget(self.opt_in_banner)

        # Follow-up Input Bar
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
        self._copy_timer.timeout.connect(self._reset_copy_btn)

        # Connections
        self.copy_btn.clicked.connect(self._on_copy)
        self.send_btn.clicked.connect(self._on_followup)
        self.followup_input.returnPressed.connect(self._on_followup)
        self.new_screen_btn.clicked.connect(self.new_screenshot_requested.emit)
        self.done_btn.clicked.connect(self.close_requested.emit)

    def _reset_copy_btn(self) -> None:
        self.copy_btn.setText("Copy")
        self.copy_btn.setIcon(get_svg_icon("copy", color=self.theme.text_secondary, size=14))

    def _on_opt_in_clicked(self, choice: bool) -> None:
        self.opt_in_banner.hide()
        self.opt_in_choice.emit(choice)

    def show_opt_in_prompt(self, show: bool = True) -> None:
        self.opt_in_banner.setVisible(show)

    def show_note(self, note: str) -> None:
        self.note_label.setText(note)
        self.note_label.show()

    def hide_note(self) -> None:
        self.note_label.hide()

    def set_answer(self, markdown_text: str, question: str = "", is_first_answer: bool = True) -> None:
        """Display answer with Pygments-enhanced markdown and Cascadia Code / Consolas font."""
        if is_first_answer:
            if "Extract all visible text in this image verbatim" in question:
                self.header_title.setText("Extracted Text (Copied to Clipboard)")
            else:
                self.header_title.setText("Answer")
            self.header_title.show()
        else:
            self.header_title.hide()

        if question:
            self.question_header.setText(f"Q: {question}")
            self.question_header.show()
        else:
            self.question_header.hide()

        # Format monospace code blocks with Cascadia Code then Consolas
        code_bg = self.theme.secondary
        code_border = self.theme.border
        text_color = self.theme.text
        doc = self.browser.document()
        doc.setDefaultStyleSheet(f"""
            pre {{
                background-color: {code_bg};
                border: 1px solid {code_border};
                border-radius: 8px;
                padding: 10px;
                font-family: 'Cascadia Code', Consolas, 'Courier New', monospace;
                font-size: 12px;
                color: {text_color};
                line-height: 1.45;
            }}
            code {{
                background-color: {code_bg};
                border-radius: 4px;
                padding: 2px 4px;
                font-family: 'Cascadia Code', Consolas, 'Courier New', monospace;
                font-size: 12px;
                color: {self.theme.pink};
            }}
            p {{ margin-bottom: 6px; }}
            ul, ol {{ margin-left: 16px; margin-bottom: 6px; }}
        """)

        # Set markdown text (ensuring full text search and copy compatibility)
        self.browser.setMarkdown(markdown_text)

        self.copy_btn.setText("Copy")
        self.copy_btn.setIcon(get_svg_icon("copy", color=self.theme.text_secondary, size=14))
        self.followup_input.clear()
        self.send_btn.setEnabled(True)
        self.followup_input.setEnabled(True)

    def _on_copy(self) -> None:
        text = self.browser.toPlainText()
        clipboard = QGuiApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        get_sound_manager().play("copy")
        self.copy_btn.setText("Copied!")
        self.copy_btn.setIcon(get_svg_icon("check", color=self.theme.success, size=14))
        self.toast.show_toast("Copied to clipboard")
        self._copy_timer.start(1500)

    def _on_followup(self) -> None:
        q = self.followup_input.text().strip()
        if q:
            self.send_btn.setEnabled(False)
            self.followup_input.setEnabled(False)
            self.followup_requested.emit(q)


class ErrorView(QWidget):
    """View 4: Friendly error display with Retry and Cancel options."""

    retry_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.theme = theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 20)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Error Icon
        self.icon_label = QLabel()
        self.icon_label.setPixmap(get_svg_pixmap("close", color=theme.error, size=28))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        # Error title
        self.title_label = QLabel("Something went wrong")
        self.title_label.setFont(get_app_font(14, QFont.Weight.DemiBold))
        self.title_label.setStyleSheet(f"color: {theme.error};")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        # Error detail message
        self.error_label = QLabel()
        self.error_label.setFont(get_app_font(12))
        self.error_label.setStyleSheet(f"color: {theme.text_secondary};")
        self.error_label.setWordWrap(True)
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.error_label)

        # Action Buttons row
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 8, 0, 0)
        btn_layout.setSpacing(8)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("secondaryButton")
        self.cancel_btn.setFont(get_app_font(12))

        self.retry_btn = QPushButton("Retry")
        self.retry_btn.setObjectName("primaryButton")
        self.retry_btn.setFont(get_app_font(12, QFont.Weight.DemiBold))

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.retry_btn)
        layout.addLayout(btn_layout)

        self.retry_btn.clicked.connect(self.retry_requested.emit)
        self.cancel_btn.clicked.connect(self.cancel_requested.emit)

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_requested.emit()
        else:
            super().keyPressEvent(event)


class MinimizedPillWidget(QWidget):
    """Floating compact brand orb pill shown when Peachy is minimized."""

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

        self.orb = BrandOrb(size=18, parent=self)
        layout.addWidget(self.orb)

        self.label = QLabel("peachy")
        self.label.setFont(get_app_font(13, QFont.Weight.DemiBold))
        self.label.setStyleSheet(f"color: {theme.pink};")
        layout.addWidget(self.label)
        layout.addStretch()

        self._drag_pos: Optional[QPoint] = None

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(self.theme.surface))
        painter.setPen(QColor(self.theme.border))
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
            self.clicked.emit()
            event.accept()


class PeachyPopup(QWidget):
    """The complete Peachy Cute Popup Window with Midnight styling and polite behavior."""

    send_question = Signal(str)
    send_followup = Signal(str)
    retry_requested = Signal()
    new_screenshot_requested = Signal()
    cancelled = Signal()
    length_changed = Signal(str)  # "short" or "detailed"
    history_requested = Signal()
    opt_in_choice = Signal(bool)

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
        """Build header bar with brand orb, wordmark, length chip, and vector icon controls."""
        self.header = QWidget(self.card)
        self.header.setCursor(Qt.CursorShape.SizeAllCursor)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 4)
        header_layout.setSpacing(8)

        # Brand Orb Mark
        self.orb = BrandOrb(size=22, parent=self.header)
        header_layout.addWidget(self.orb)

        # Title
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        self.title_label = QLabel("peachy")
        self.title_label.setObjectName("headerTitle")
        self.title_label.setFont(get_app_font(15, QFont.Weight.DemiBold))
        title_box.addWidget(self.title_label)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        # Length Chip ("Short" / "Detailed") with vector chevron icon
        self.chip_btn = QPushButton("Short" if self._answer_length == "short" else "Detailed")
        self.chip_btn.setObjectName("chipButton")
        self.chip_btn.setIcon(get_svg_icon("chevron_down", color=self.theme.text_secondary, size=12))
        self.chip_btn.setFont(get_app_font(11))
        self.chip_btn.setToolTip("Click to toggle Short / Detailed answers")
        self.chip_btn.clicked.connect(self._toggle_length_chip)
        header_layout.addWidget(self.chip_btn)

        # History Button (vector clock SVG icon, zero emoji)
        self.history_btn = QPushButton()
        self.history_btn.setObjectName("iconButton")
        self.history_btn.setIcon(get_svg_icon("history", color=self.theme.text_secondary, size=16))
        self.history_btn.setToolTip("Chat History (Ctrl+Shift+H)")
        self.history_btn.clicked.connect(self.history_requested.emit)
        header_layout.addWidget(self.history_btn)

        # Action Buttons (Pin, Minimize, Close with vector SVG icons)
        self.pin_btn = QPushButton()
        self.pin_btn.setObjectName("iconButton")
        self.pin_btn.setCheckable(True)
        self.pin_btn.setChecked(self._is_pinned)
        self.pin_btn.setIcon(get_svg_icon("pin" if self._is_pinned else "unpin", color=self.theme.pink if self._is_pinned else self.theme.text_secondary, size=16))
        self.pin_btn.setToolTip("Unpin window" if self._is_pinned else "Pin to stay on top")
        self.pin_btn.clicked.connect(self._toggle_pin)
        header_layout.addWidget(self.pin_btn)

        self.minimize_btn = QPushButton()
        self.minimize_btn.setObjectName("iconButton")
        self.minimize_btn.setIcon(get_svg_icon("minimize", color=self.theme.text_secondary, size=16))
        self.minimize_btn.setToolTip("Minimize to floating pill")
        self.minimize_btn.clicked.connect(self.minimize_to_pill)
        header_layout.addWidget(self.minimize_btn)

        self.close_btn = QPushButton()
        self.close_btn.setObjectName("iconButton")
        self.close_btn.setIcon(get_svg_icon("close", color=self.theme.text_secondary, size=16))
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
        self.answer_view.opt_in_choice.connect(self.opt_in_choice.emit)

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

    def set_answer_length(self, length: str) -> None:
        """Set answer length mode ('short' or 'detailed') and update chip UI."""
        self._answer_length = "detailed" if str(length).lower() == "detailed" else "short"
        if hasattr(self, "chip_btn"):
            self.chip_btn.setText("Detailed" if self._answer_length == "detailed" else "Short")

    @property
    def pinned(self) -> bool:
        return self._is_pinned

    @pinned.setter
    def pinned(self, value: bool) -> None:
        self.set_pinned(value)

    def set_pinned(self, pinned: bool) -> None:
        """Set pinned stay-on-top status and update button UI."""
        self._is_pinned = bool(pinned)
        if hasattr(self, "pin_btn"):
            self.pin_btn.setChecked(self._is_pinned)
            self.pin_btn.setIcon(get_svg_icon("pin" if self._is_pinned else "unpin", color=self.theme.pink if self._is_pinned else self.theme.text_secondary, size=16))
            self.pin_btn.setToolTip("Unpin window" if self._is_pinned else "Pin to stay on top")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._is_pinned)
        if self.isVisible():
            self.show()

    def _toggle_pin(self) -> None:
        self.set_pinned(not self._is_pinned)

    def minimize_to_pill(self) -> None:
        """Collapse main card into the small floating brand orb pill."""
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
        self.hide_note()
        self.show_opt_in_prompt(False)
        self.ask_view.set_thumbnail(pixmap)
        self.stack.setCurrentIndex(ViewIndex.ASK)

        get_sound_manager().play("open")

        # AskView needs focus
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.show()
        self.raise_()
        self.activateWindow()
        self.ask_view.focus_input()

    def show_opt_in_prompt(self, show: bool = True) -> None:
        """Show or hide the one-time history opt-in banner."""
        self.answer_view.show_opt_in_prompt(show)

    def show_note(self, text: str) -> None:
        """Display contextual note in the answer view."""
        self.answer_view.show_note(text)

    def hide_note(self) -> None:
        """Hide contextual note in the answer view."""
        self.answer_view.hide_note()

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

        get_sound_manager().play("answer")

        # Enforce polite focus: Answer view appears without stealing focus
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.show()
        self.raise_()

    def show_error(self, message: str) -> None:
        """Display Error view."""
        self.error_view.set_error(message)
        self.stack.setCurrentIndex(ViewIndex.ERROR)
        get_sound_manager().play("error")
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

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self.cancelled.emit()
        super().closeEvent(event)
