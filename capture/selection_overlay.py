"""Frozen selection overlay for multi-monitor screen capture.

Features:
- Exactly one frameless, topmost Qt.Tool window per connected monitor.
- Zero taskbar entry.
- 35% black dimming over unselected areas.
- 2px pink border (#F472B6) and light pink tint inside the selection.
- Physical pixel dimension label (width x height) clamped cleanly within view.
- Crosshair cursor.
- Clamped drag staying on the monitor where drag started.
- Esc / Right-Click cancels; Enter / Mouse release confirms; Backspace clears.
- Min 8x8 physical pixel size threshold.
- 60-second inactivity safety timeout.
- Automatic foreground restoration on cancel.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QRegion,
    QScreen,
)
from PySide6.QtWidgets import QWidget

from capture.geometry import (
    clamp_rect,
    extract_crop,
    is_valid_selection,
    logical_to_physical,
    normalize_rect,
)
from capture.screen_capture import CapturedMonitor
from core import win32

logger = logging.getLogger(__name__)

# Visual style constants
COLOR_DIM = QColor(0, 0, 0, 90)              # ~35% black dimming
COLOR_BORDER = QColor(244, 114, 182)          # #F472B6
COLOR_TINT = QColor(244, 114, 182, 35)        # Light pink tint
COLOR_PILL_BG = QColor(20, 20, 25, 210)       # Dark pill background
COLOR_PILL_TEXT = QColor(255, 255, 255)       # White text
BORDER_WIDTH = 2
MIN_SELECTION_PIXELS = 8


class SelectionOverlay(QWidget):
    """Full-screen frameless overlay for a single monitor displaying its frozen pixmap."""

    def __init__(self, captured: CapturedMonitor, manager: OverlayManager):
        super().__init__(None)
        self.captured = captured
        self.manager = manager

        # Drag state (all in local widget coordinates)
        self.start_pos: Optional[QPoint] = None
        self.current_pos: Optional[QPoint] = None
        self.is_dragging: bool = False
        self.selection_rect: Optional[QRect] = None

        self._init_window()

    def _init_window(self) -> None:
        """Configure frameless, topmost, tool window properties and position."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Position precisely over this screen's logical geometry
        if isinstance(self.captured.screen, QScreen):
            self.setScreen(self.captured.screen)
        self.setGeometry(self.captured.logical_geometry)

    def clear_selection(self) -> None:
        """Clear active rectangle on this overlay."""
        self.start_pos = None
        self.current_pos = None
        self.is_dragging = False
        self.selection_rect = None
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)

        # 1. Paint native frozen pixmap (Qt scales device-independently using DPR)
        painter.drawPixmap(0, 0, self.captured.pixmap)

        # 2. Dimming & Selection Highlights
        if not self.selection_rect or self.selection_rect.isEmpty():
            # Whole screen dimmed
            painter.fillRect(self.rect(), COLOR_DIM)
        else:
            # Dim outside selection using region subtraction
            outside_region = QRegion(self.rect()).subtracted(QRegion(self.selection_rect))
            painter.setClipRegion(outside_region)
            painter.fillRect(self.rect(), COLOR_DIM)
            painter.setClipping(False)

            # Inside selection: light tint + 2px border
            painter.fillRect(self.selection_rect, COLOR_TINT)

            pen = QPen(COLOR_BORDER, BORDER_WIDTH)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            # Adjust rect slightly to keep stroke within bounds
            painter.drawRect(self.selection_rect.adjusted(0, 0, -1, -1))

            # 3. Dimension Pill Label
            self._paint_pill_label(painter, self.selection_rect)

        painter.end()

    def _paint_pill_label(self, painter: QPainter, rect: QRect) -> None:
        """Draw a pill badge showing width x height in physical pixels."""
        dpr = self.captured.dpr
        pw = round(rect.width() * dpr)
        ph = round(rect.height() * dpr)
        label_text = f"{pw} × {ph}"

        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(label_text)
        text_h = fm.height()

        pill_w = text_w + 16
        pill_h = text_h + 8

        # Position below selection by default; flip above if too close to bottom edge
        x = rect.center().x() - pill_w // 2
        y = rect.bottom() + 8
        if y + pill_h > self.height() - 8:
            y = rect.top() - pill_h - 8

        # Clamp pill coordinates within screen
        x = max(8, min(x, self.width() - pill_w - 8))
        y = max(8, min(y, self.height() - pill_h - 8))

        pill_rect = QRect(x, y, pill_w, pill_h)

        # Draw rounded badge
        painter.setBrush(COLOR_PILL_BG)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(pill_rect, 5, 5)

        # Draw text
        painter.setPen(COLOR_PILL_TEXT)
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, label_text)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.manager.notify_activity()

        if event.button() == Qt.MouseButton.RightButton:
            self.manager.cancel()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            # Clear selection on other overlays
            self.manager.clear_other_selections(self)

            pos = event.position().toPoint()
            self.start_pos = pos
            self.current_pos = pos
            self.is_dragging = True
            self.selection_rect = None
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.manager.notify_activity()

        if self.is_dragging and self.start_pos is not None:
            # Clamp drag coordinates within this monitor
            pos = event.position().toPoint()
            cur_x = max(0, min(pos.x(), self.width()))
            cur_y = max(0, min(pos.y(), self.height()))
            self.current_pos = QPoint(cur_x, cur_y)

            # Compute normalized rect
            x, y, w, h = normalize_rect(
                self.start_pos.x(),
                self.start_pos.y(),
                self.current_pos.x(),
                self.current_pos.y(),
            )
            self.selection_rect = QRect(x, y, w, h)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.manager.notify_activity()

        if event.button() == Qt.MouseButton.LeftButton and self.is_dragging:
            self.is_dragging = False
            if self.selection_rect:
                pw = round(self.selection_rect.width() * self.captured.dpr)
                ph = round(self.selection_rect.height() * self.captured.dpr)

                if is_valid_selection(pw, ph, MIN_SELECTION_PIXELS, MIN_SELECTION_PIXELS):
                    # Valid selection: confirm immediately
                    self.manager.confirm_selection(self, self.selection_rect)
                else:
                    # Under 8x8 physical pixels: ignore
                    self.clear_selection()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        self.manager.notify_activity()
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self.manager.cancel()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.selection_rect:
                pw = round(self.selection_rect.width() * self.captured.dpr)
                ph = round(self.selection_rect.height() * self.captured.dpr)
                if is_valid_selection(pw, ph, MIN_SELECTION_PIXELS, MIN_SELECTION_PIXELS):
                    self.manager.confirm_selection(self, self.selection_rect)
        elif key == Qt.Key.Key_Backspace:
            self.clear_selection()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        """Handle Alt+F4 or window closure gracefully by cancelling selection."""
        if self.manager and self in self.manager.overlays:
            self.manager.overlays.remove(self)
            self.manager.cancel()
        super().closeEvent(event)


class OverlayManager(QWidget):
    """Coordinates selection overlays across all connected monitors."""

    crop_confirmed = Signal(QImage)
    cancelled = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.overlays: List[SelectionOverlay] = []
        self.saved_foreground_hwnd: int = 0

        # Safety timeout: cancel if inactive for 60 seconds
        self.safety_timer = QTimer(self)
        self.safety_timer.setSingleShot(True)
        self.safety_timer.timeout.connect(self._on_timeout)

        # Monitor topology change listener (cancel safely if monitor plugged/unplugged)
        app = QGuiApplication.instance()
        if app:
            app.screenAdded.connect(self._on_screens_changed)
            app.screenRemoved.connect(self._on_screens_changed)

    def _on_screens_changed(self, *args) -> None:
        if self.overlays:
            logger.info("Screen topology changed during selection. Cancelling selection safely.")
            self.cancel()

    def start_selection(
        self, captured_monitors: List[CapturedMonitor], foreground_hwnd: int = 0
    ) -> None:
        """Display frozen overlays on all monitors and begin selection."""
        self.cleanup()
        self.saved_foreground_hwnd = foreground_hwnd

        if not captured_monitors:
            logger.warning("No captured monitors to display.")
            self.cancel()
            return

        cursor_pos = QCursor.pos()
        focused_overlay: Optional[SelectionOverlay] = None

        for mon in captured_monitors:
            overlay = SelectionOverlay(mon, self)
            self.overlays.append(overlay)
            overlay.show()
            overlay.raise_()

            # Identify the monitor containing the mouse cursor
            if mon.logical_geometry.contains(cursor_pos):
                focused_overlay = overlay

        # Ensure active monitor gets keyboard focus immediately
        target_overlay = focused_overlay or (self.overlays[0] if self.overlays else None)
        if target_overlay is not None:
            target_overlay.activateWindow()
            win32.set_foreground_window(target_overlay.winId())

        # Start 60s safety timeout
        self.notify_activity()
        logger.info("Selection overlays displayed across %d monitor(s)", len(self.overlays))

    def notify_activity(self) -> None:
        """Reset the 60s inactivity safety timer."""
        self.safety_timer.start(60_000)

    def _on_timeout(self) -> None:
        logger.info("Selection cancelled due to 60s inactivity safety timeout.")
        self.cancel()

    def clear_other_selections(self, active_overlay: SelectionOverlay) -> None:
        """Ensure only one monitor has an active selection rectangle."""
        for ov in self.overlays:
            if ov is not active_overlay:
                ov.clear_selection()

    def confirm_selection(self, overlay: SelectionOverlay, logical_rect: QRect) -> None:
        """Extract cropped physical QImage and clean up overlays."""
        self.safety_timer.stop()

        dpr = overlay.captured.dpr
        px = round(logical_rect.x() * dpr)
        py = round(logical_rect.y() * dpr)
        pw = round(logical_rect.width() * dpr)
        ph = round(logical_rect.height() * dpr)

        cropped_img = extract_crop(overlay.captured.image, (px, py, pw, ph))
        logger.info("Crop confirmed: %d x %d physical px (DPR %.2f)", pw, ph, dpr)

        # Record selection geometry and target screen for popup positioning
        global_origin = overlay.geometry().topLeft()
        self.last_selection_rect = QRect(global_origin + logical_rect.topLeft(), logical_rect.size())
        self.last_screen = overlay.captured.screen

        self.cleanup()

        # Emit confirmed image
        self.crop_confirmed.emit(cropped_img)

    def cancel(self) -> None:
        """Cancel selection and restore original foreground focus."""
        self.safety_timer.stop()
        logger.info("Selection cancelled.")

        self.cleanup()

        # Restore saved foreground window
        if self.saved_foreground_hwnd:
            win32.set_foreground_window(self.saved_foreground_hwnd)
            self.saved_foreground_hwnd = 0

        self.cancelled.emit()

    def cleanup(self) -> None:
        """Close and delete all overlay widgets."""
        self.safety_timer.stop()
        to_close = list(self.overlays)
        self.overlays.clear()
        for ov in to_close:
            ov.hide()
            ov.close()
            ov.deleteLater()
