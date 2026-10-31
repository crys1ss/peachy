"""Peachy brand orb mark widget with radiant gradient following the active accent.

Features (docs/REDESIGN.md Sections 3.1, 4):
- 22 px / 48 px radial orb mark.
- Linear gradient at 135° from accent to accent_2 (peach to coral rose by default).
- 1 px border at rgba(255, 255, 255, 0.18) with a subtle outer glow.
- Dynamic theme and accent updates via apply_theme.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget

from ui.theme import ThemeTokens, get_theme


class BrandOrb(QWidget):
    """Renders the glowing Peachy brand orb mark using accent -> accent_2 gradient."""

    def __init__(
        self,
        size: int = 22,
        theme: Optional[ThemeTokens] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._size = size
        self._theme = theme or get_theme()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._size, self._size)

    def apply_theme(self, theme: ThemeTokens) -> None:
        """Update orb color tokens dynamically."""
        self._theme = theme
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        center_x = w / 2.0
        center_y = h / 2.0
        radius = min(w, h) / 2.0 - 2.0

        t = self._theme

        # 1. Subtle ambient glow
        accent_col = QColor(t.accent)
        glow_grad = QRadialGradient(center_x, center_y, radius + 2.5)
        glow_grad.setColorAt(0.0, QColor(accent_col.red(), accent_col.green(), accent_col.blue(), 70))
        glow_grad.setColorAt(0.65, QColor(accent_col.red(), accent_col.green(), accent_col.blue(), 25))
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(center_x, center_y), radius + 2.0, radius + 2.0)

        # 2. Main brand orb gradient (accent -> accent_2 at 135 deg)
        diag = radius * 0.7071
        body_grad = QLinearGradient(center_x - diag, center_y - diag, center_x + diag, center_y + diag)
        body_grad.setColorAt(0.0, QColor(t.accent))
        body_grad.setColorAt(1.0, QColor(t.accent_2))

        painter.setBrush(body_grad)
        # 1 px rim at rgba(255, 255, 255, 0.18)
        border_pen = QPen(QColor(255, 255, 255, 46), 1.0)
        painter.setPen(border_pen)
        painter.drawEllipse(QPointF(center_x, center_y), radius, radius)

        # 3. Inner specular sheen (top-left gloss)
        highlight_grad = QRadialGradient(center_x - radius * 0.35, center_y - radius * 0.35, radius * 0.75)
        highlight_grad.setColorAt(0.0, QColor(255, 255, 255, 140))
        highlight_grad.setColorAt(0.5, QColor(255, 255, 255, 30))
        highlight_grad.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter.setBrush(highlight_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(
            QPointF(center_x - radius * 0.25, center_y - radius * 0.25),
            radius * 0.60,
            radius * 0.50,
        )

        painter.end()
