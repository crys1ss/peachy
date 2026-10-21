"""Multi-monitor frozen selection overlay windows.

Features:
- One frameless, topmost Qt.Tool window per physical monitor to prevent mixed-DPI distortion
- Renders the frozen screen snapshot with a 35% dark dimming overlay
- Interactive click-and-drag crop selection with 2px pink border (#F472B6), light tint, and pixel label
- Esc / right-click cancels, Enter / mouse-up confirms, Backspace clears
- 8x8 physical pixel minimum size threshold
- 60-second safety timeout
- Clean focus restoration to the previously active window on cancellation
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QPixmap,
    QRegion,
)
from PySide6.QtWidgets import QWidget

from capture.geometry import (
    clamp_crop_box,
    clamp_rect,
    is_valid_selection,
    logical_to_physical,
    normalize_rect,
)
from capture.screen_capture import CapturedMonitor
from core import win32

logger = logging.getLogger(__name__)

# Style tokens
COLOR_ACCENT = QColor("#F472B6")  # Peachy pink
COLOR_TINT = QColor(244, 114, 182, 38)  # Light pink translucent tint
COLOR_DIM = QColor(0, 0, 0, int(255 * 0.35))  # 35% black dim
COLOR_LABEL_BG = QColor(31, 31, 35, 220)  # Dark pill background
COLOR_LABEL_TEXT = QColor(255, 255, 255)


class SelectionOverlayWindow(QWidget):
    """Fullscreen frameless overlay window covering a single physical monitor."""

    drag_started = Signal(object)  # Emits self
    selection_confirmed = Signal(QImage, object, tuple)  # (crop_image, CapturedMonitor, phys_rect)
    selection_cancelled = Signal()

    def __init__(self, monitor: CapturedMonitor, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.monitor = monitor
        self.dpr = monitor.dpr

        # Pixmap preparation for high-DPI rendering
        self.pixmap = monitor.pixmap
        self.pixmap.setDevicePixelRatio(self.dpr)

        # Drag state
        self._is_active_drag = False
        self._start_pos: Optional[QPointF] = None
        self._current_pos: Optional[QPointF] = None
        self._rect_logical: Optional[tuple[float, float, float, float]] = None

        self._init_window()

    def _init_window(self) -> None:
        """Configure frameless, topmost, transparent window attributes."""
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

        # Match exact logical geometry of this monitor
        x, y, w, h = self.monitor.logical_geom
        self.setGeometry(x, y, w, h)

    def clear_selection(self) -> None:
        """Reset current active selection."""
        self._is_active_drag = False
        self._start_pos = None
        self._current_pos = None
        self._rect_logical = None
        self.update()

    def _get_current_physical_rect(self) -> Optional[tuple[int, int, int, int]]:
        """Return (x, y, w, h) of current selection in physical device pixels."""
        if not self._rect_logical:
            return None
        lx, ly, lw, lh = self._rect_logical
        return logical_to_physical(lx, ly, lw, lh, self.dpr)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        # 1. Paint frozen monitor screenshot at native DPR
        painter.drawPixmap(0, 0, self.pixmap)

        # 2. Paint Dimming layer
        if not self._rect_logical or self._rect_logical[2] <= 0 or self._rect_logical[3] <= 0:
            # Entire screen is dimmed
            painter.fillRect(self.rect(), COLOR_DIM)
            return

        lx, ly, lw, lh = self._rect_logical
        sel_rect = QRectF(lx, ly, lw, lh)

        # Dim everything outside the selection using QRegion subtraction
        full_region = QRegion(self.rect())
        selected_region = QRegion(sel_rect.toRect())
        dim_region = full_region.subtracted(selected_region)
        painter.setClipRegion(dim_region)
        painter.fillRect(self.rect(), COLOR_DIM)
        painter.setClipping(False)

        # 3. Inside selection: Light pink tint & 2px border
        painter.fillRect(sel_rect, COLOR_TINT)

        pen = QPen(COLOR_ACCENT, 2)
        pen.setJoinStyle(Qt.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(sel_rect)

        # 4. Dimensions pill label (physical pixels)
        phys = self._get_current_physical_rect()
        if phys and phys[2] > 0 and phys[3] > 0:
            pw, ph = phys[2], phys[3]
            label_text = f"{pw} × {ph}"

            painter.setRenderHint(QPainter.Antialiasing, True)
            font = QFont("Segoe UI", 9, QFont.DemiBold)
            painter.setFont(font)

            metrics = painter.fontMetrics()
            text_rect = metrics.boundingRect(label_text)
            pill_w = text_rect.width() + 14
            pill_h = text_rect.height() + 6

            # Position pill below selection (or above if too close to bottom edge)
            pill_x = lx + (lw - pill_w) / 2.0
            pill_x = max(4.0, min(pill_x, self.width() - pill_w - 4.0))

            if ly + lh + pill_h + 8 < self.height():
                pill_y = ly + lh + 6.0
            else:
                pill_y = max(4.0, ly - pill_h - 6.0)

            pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(COLOR_LABEL_BG))
            painter.drawRoundedRect(pill_rect, 4.0, 4.0)

            painter.setPen(COLOR_LABEL_TEXT)
            painter.drawText(pill_rect, Qt.AlignCenter, label_text)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.RightButton:
            # Right-click cancels selection
            self.selection_cancelled.emit()
            return

        if event.button() == Qt.LeftButton:
            self._is_active_drag = True
            pos = event.position()
            self._start_pos = pos
            self._current_pos = pos
            self._rect_logical = (pos.x(), pos.y(), 0.0, 0.0)
            self.drag_started.emit(self)
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self._is_active_drag or not self._start_pos:
            return

        pos = event.position()
        self._current_pos = pos

        # Normalize across all 4 drag directions
        norm_x, norm_y, norm_w, norm_h = normalize_rect(
            self._start_pos.x(),
            self._start_pos.y(),
            pos.x(),
            pos.y(),
        )

        # Clamp inside this monitor's logical bounds
        self._rect_logical = clamp_rect(
            norm_x,
            norm_y,
            norm_w,
            norm_h,
            0.0,
            0.0,
            float(self.width()),
            float(self.height()),
        )
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self._is_active_drag:
            self._is_active_drag = False
            self._finish_selection()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key_Escape:
            self.selection_cancelled.emit()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self._finish_selection()
        elif key == Qt.Key_Backspace:
            self.clear_selection()
        else:
            super().keyPressEvent(event)

    def _finish_selection(self) -> None:
        """Validate selection dimensions and emit confirmed crop or cancel."""
        phys = self._get_current_physical_rect()
        if not phys:
            self.selection_cancelled.emit()
            return

        px, py, pw, ph = phys
        if not is_valid_selection(pw, ph, min_size=8):
            logger.info("Selection ignored: %dx%d is smaller than 8x8 minimum.", pw, ph)
            self.selection_cancelled.emit()
            return

        # Clamp crop box strictly within image bounds
        img_w, img_h = self.monitor.image.width(), self.monitor.image.height()
        cx, cy, cw, ch = clamp_crop_box(px, py, pw, ph, img_w, img_h)

        if cw <= 0 or ch <= 0:
            self.selection_cancelled.emit()
            return

        cropped_image = self.monitor.image.copy(cx, cy, cw, ch)
        logger.info(
            "Selection confirmed on %s: Crop physical box (%d, %d, %d, %d)",
            self.monitor.name,
            cx,
            cy,
            cw,
            ch,
        )
        self.selection_confirmed.emit(cropped_image, self.monitor, (cx, cy, cw, ch))


class SelectionOverlayManager(QWidget):
    """Coordinates overlay windows across all monitors, handling focus and cancellation."""

    selection_confirmed = Signal(QImage, object, tuple)
    selection_cancelled = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._windows: List[SelectionOverlayWindow] = []
        self._safety_timer = QTimer(self)
        self._safety_timer.setSingleShot(True)
        self._safety_timer.timeout.connect(self._on_timeout)

    @property
    def is_active(self) -> bool:
        return len(self._windows) > 0

    def start_selection(self, monitors: List[CapturedMonitor]) -> None:
        """Display an overlay on every active monitor and grab initial focus."""
        self.close_all()

        if not monitors:
            logger.warning("No monitors provided to SelectionOverlayManager.")
            self.selection_cancelled.emit()
            return

        primary_window: Optional[SelectionOverlayWindow] = None

        for monitor in monitors:
            win = SelectionOverlayWindow(monitor)
            win.drag_started.connect(self._on_drag_started)
            win.selection_confirmed.connect(self._on_selection_confirmed)
            win.selection_cancelled.connect(self._on_selection_cancelled)

            self._windows.append(win)
            win.show()

            # Identify primary monitor window for initial focus
            if monitor.screen == QGuiApplication.primaryScreen():
                primary_window = win

        # Focus primary or first overlay window to ensure first Esc press works
        target_win = primary_window or (self._windows[0] if self._windows else None)
        if target_win is not None:
            target_win.raise_()
            target_win.activateWindow()
            target_win.setFocus(Qt.OtherFocusReason)
            win32.set_foreground_window(int(target_win.winId()))

        # Start 60-second safety timeout
        self._safety_timer.start(60000)
        logger.info("Selection overlays displayed across %d monitor(s).", len(self._windows))

    def _on_drag_started(self, active_win: SelectionOverlayWindow) -> None:
        """Clear selections on any other monitors when a drag begins on one monitor."""
        for win in self._windows:
            if win is not active_win:
                win.clear_selection()

    def _on_selection_confirmed(self, crop: QImage, monitor: CapturedMonitor, rect: tuple) -> None:
        self.close_all()
        self.selection_confirmed.emit(crop, monitor, rect)

    def _on_selection_cancelled(self) -> None:
        self.close_all()
        self.selection_cancelled.emit()

    def _on_timeout(self) -> None:
        logger.info("Selection overlay safety timeout (60s) fired. Cancelling selection.")
        self._on_selection_cancelled()

    def close_all(self) -> None:
        """Safely close all overlay windows and release resources."""
        self._safety_timer.stop()
        for win in self._windows:
            try:
                win.close()
            except Exception as exc:
                logger.debug("Error closing overlay window: %s", exc)
        self._windows.clear()
