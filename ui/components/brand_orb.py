"""Peachy brand orb mark widget with radiant gradient and peach highlight.

The brand orb is the primary visual mark of Peachy:
- Pink (#FF6BCE) to Lavender (#B9A4FF) core gradient
- Pink Soft (#F5A4DE) specular rim
- Peach (#FF9E7D) highlight used strictly within the orb gradient
- Smooth anti-aliased rendering with outer ambient glow
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget


class BrandOrb(QWidget):
    """Renders the glowing Peachy brand orb mark."""

    def __init__(self, size: int = 22, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._size = size

    def sizeHint(self) -> QSize:
        return QSize(self._size, self._size)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        center_x = w / 2.0
        center_y = h / 2.0
        radius = min(w, h) / 2.0 - 1.5

        # 1. Subtle ambient glow
        glow_grad = QRadialGradient(center_x, center_y, radius + 2.0)
        glow_grad.setColorAt(0.0, QColor(255, 107, 206, 90))    # Pink #FF6BCE with alpha
        glow_grad.setColorAt(0.6, QColor(255, 158, 125, 45))    # Peach #FF9E7D highlight
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(center_x, center_y), radius + 1.5, radius + 1.5)

        # 2. Main brand orb gradient
        # Angle from top-left to bottom-right
        body_grad = QLinearGradient(center_x - radius, center_y - radius, center_x + radius, center_y + radius)
        body_grad.setColorAt(0.00, QColor("#FF6BCE"))  # Pink
        body_grad.setColorAt(0.35, QColor("#F5A4DE"))  # Pink Soft
        body_grad.setColorAt(0.70, QColor("#B9A4FF"))  # Lavender
        body_grad.setColorAt(1.00, QColor("#FF9E7D"))  # Peach highlight

        painter.setBrush(body_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(center_x, center_y), radius, radius)

        # 3. Inner specular crescent / sheen (top-left gloss)
        highlight_grad = QRadialGradient(center_x - radius * 0.35, center_y - radius * 0.35, radius * 0.8)
        highlight_grad.setColorAt(0.0, QColor(255, 255, 255, 160))
        highlight_grad.setColorAt(0.5, QColor(245, 164, 222, 60))
        highlight_grad.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter.setBrush(highlight_grad)
        painter.drawEllipse(
            QPointF(center_x - radius * 0.25, center_y - radius * 0.25),
            radius * 0.65,
            radius * 0.55,
        )

        painter.end()

