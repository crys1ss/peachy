"""Toast notification overlay for instant action feedback.

Features:
- Frameless floating pill with Midnight styling (#1E1E29 elevated background, #292735 border)
- Vector check icon (#79E2B5)
- Smooth opacity fade in/out respecting Windows motion reduction
- Auto-dismisses after timeout
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ui.components.icons import get_svg_pixmap
from ui.theme import get_app_font


class Toast(QFrame):
    """Floating feedback toast notification."""

    def __init__(self, message: str = "Copied to clipboard", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("toastPill")
        self.setStyleSheet("""
            QFrame#toastPill {
                background-color: #1E1E29;
                border: 1px solid #292735;
                border-radius: 14px;
                padding: 4px 12px;
            }
            QLabel {
                color: #F6F3FA;
                font-size: 12px;
                font-weight: 500;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 10, 4)
        layout.setSpacing(6)

        # Vector check icon
        self.icon_label = QLabel(self)
        self.icon_label.setPixmap(get_svg_pixmap("check", color="#79E2B5", size=14))
        layout.addWidget(self.icon_label)

        # Message label
        self.label = QLabel(message, self)
        self.label.setFont(get_app_font(12))
        layout.addWidget(self.label)

        # Opacity effect for fade animation
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)

        self._anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)

        # Dismiss timer
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_toast)

        self.hide()

    def show_toast(self, message: Optional[str] = None, duration_ms: int = 1500, animate: bool = True) -> None:
        """Display toast with message and auto-dismiss after duration_ms."""
        if message:
            self.label.setText(message)

        self.adjustSize()
        if self.parentWidget():
            # Center near the bottom of parent widget
            pw = self.parentWidget().width()
            ph = self.parentWidget().height()
            w = self.width()
            h = self.height()
            self.move(int((pw - w) / 2), int(ph - h - 16))

        self.show()
        self.raise_()

        if animate:
            self._anim.stop()
            self._anim.setDuration(120)
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self._anim.start()
        else:
            self._opacity_effect.setOpacity(1.0)

        self._timer.start(duration_ms)

    def hide_toast(self, animate: bool = True) -> None:
        """Fade out toast and hide."""
        if animate and self.isVisible():
            self._anim.stop()
            self._anim.setDuration(120)
            self._anim.setStartValue(self._opacity_effect.opacity())
            self._anim.setEndValue(0.0)
            self._anim.setEasingCurve(QEasingCurve.Type.InQuad)
            self._anim.finished.connect(self._on_fade_out_finished)
            self._anim.start()
        else:
            self._opacity_effect.setOpacity(0.0)
            self.hide()

    def _on_fade_out_finished(self) -> None:
        try:
            self._anim.finished.disconnect(self._on_fade_out_finished)
        except Exception:
            pass
        self.hide()

