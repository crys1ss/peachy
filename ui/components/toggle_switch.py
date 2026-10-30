"""Animated pill toggle switch component for Peachy.

Features (docs/REDESIGN.md Sections 3.3, 5):
- Fully rounded pill track (38x20 px) with sliding thumb circle (14 px).
- Smooth 140 ms OutCubic thumb animation, snapping instantly (0 ms) when motion reduction is active.
- Keyboard accessible via Space / Enter keys, standard QAbstractButton signals (toggled, clicked).
- Dynamic runtime theme & accent support via apply_theme.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QAbstractButton, QWidget

from ui.motion import duration, should_animate
from ui.theme import ThemeTokens, get_theme


class ToggleSwitch(QAbstractButton):
    """Animated pill toggle switch component."""

    def __init__(
        self,
        checked: bool = False,
        theme: Optional[ThemeTokens] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._theme = theme or get_theme()
        # Normalized thumb position: 0.0 (off) to 1.0 (on)
        self._thumb_pos: float = 1.0 if checked else 0.0

        self._anim = QPropertyAnimation(self, b"thumb_position", self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.toggled.connect(self._on_toggled)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(40, 24)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(38, 20)

    def get_thumb_position(self) -> float:
        return self._thumb_pos

    def set_thumb_position(self, pos: float) -> None:
        self._thumb_pos = float(pos)
        self.update()

    thumb_position = Property(float, get_thumb_position, set_thumb_position)

    def apply_theme(self, theme: ThemeTokens) -> None:
        """Update switch color tokens dynamically."""
        self._theme = theme
        self.update()

    def _on_toggled(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        anim_ms = duration(140)
        if anim_ms == 0:
            self._thumb_pos = target
            self.update()
            return

        self._anim.stop()
        self._anim.setDuration(anim_ms)
        self._anim.setStartValue(self._thumb_pos)
        self._anim.setEndValue(target)
        self._anim.start()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = 38.0
        h = 20.0
        # Center horizontally and vertically within bounding widget
        rect_x = (self.width() - w) / 2.0
        rect_y = (self.height() - h) / 2.0
        track_rect = QRectF(rect_x, rect_y, w, h)
        radius = h / 2.0

        # Colors based on theme and checked progress
        t = self._theme
        if not self.isEnabled():
            bg_color = QColor(t.border)
            border_color = QColor(t.hairline)
            thumb_color = QColor(t.text_tertiary)
        elif self._thumb_pos > 0.05:
            # Active (accent) or transitioning
            bg_active = QColor(t.accent)
            bg_inactive = QColor(t.secondary if t.is_dark else t.border)
            r = int(bg_inactive.red() + (bg_active.red() - bg_inactive.red()) * self._thumb_pos)
            g = int(bg_inactive.green() + (bg_active.green() - bg_inactive.green()) * self._thumb_pos)
            b = int(bg_inactive.blue() + (bg_active.blue() - bg_inactive.blue()) * self._thumb_pos)
            bg_color = QColor(r, g, b)
            border_color = bg_color
            thumb_color = QColor(t.accent_ink if t.is_dark else "#FFFFFF")
        else:
            bg_color = QColor(t.secondary if t.is_dark else t.hover)
            border_color = QColor(t.border)
            thumb_color = QColor(t.text_secondary)

        # Draw pill track
        painter.setPen(border_color)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(track_rect, radius, radius)

        # Draw focus outline if focused
        if self.hasFocus():
            focus_pen = QColor(t.accent)
            focus_pen.setAlpha(120)
            painter.setPen(focus_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(track_rect.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)

        # Draw sliding thumb circle (14 px diameter)
        thumb_diameter = 14.0
        thumb_radius = thumb_diameter / 2.0
        padding = 3.0
        min_cx = rect_x + padding + thumb_radius
        max_cx = rect_x + w - padding - thumb_radius
        cx = min_cx + (max_cx - min_cx) * self._thumb_pos
        cy = rect_y + h / 2.0

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(thumb_color)
        painter.drawEllipse(QPointF(cx, cy), thumb_radius, thumb_radius)
        painter.end()
