"""Frozen selection overlay for multi-monitor screen capture.

Features:
- Dual selection modes: Freehand (default) and Rectangle.
- Tab key switches mode during selection.
- Top hint chip showing mode and key shortcuts.
- Smooth live drawing of 3 px pink stroke (#F472B6) with round caps and Euclidean distance filtering.
- Shift held on mouse release keeps selection open and adds additional strokes (union of shapes).
- Enter confirms; Backspace clears strokes; Esc / Right-Click cancels.
- Exactly one frameless, topmost Qt.Tool window per connected monitor.
- Zero taskbar entry.
- 35% black dimming over unselected areas.
- Light pink tint (#F472B6) inside selections.
- Physical pixel dimension label clamped cleanly within view.
- Crosshair cursor.
- Stroke stays on the monitor where it started and clamps to screen edges.
- Degenerate inputs ignored (< 8x8 physical px, < 64 sq px area, straight line, single click).
- 60-second inactivity safety timeout.
- Automatic foreground restoration on cancel.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

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
    QPainterPath,
    QPen,
    QPolygon,
    QRegion,
    QScreen,
)
from PySide6.QtWidgets import QWidget

from capture.geometry import (
    add_point_if_far_enough,
    clamp_rect,
    close_path,
    crop_freehand,
    extract_crop,
    is_degenerate_stroke,
    is_valid_selection,
    logical_to_physical,
    normalize_rect,
    polygon_bounding_box,
    union_bounding_boxes,
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

        # Rectangle mode drag state (local logical widget coordinates)
        self.start_pos: Optional[QPoint] = None
        self.current_pos: Optional[QPoint] = None
        self.is_dragging: bool = False
        self.selection_rect: Optional[QRect] = None

        # Freehand mode state
        self.is_drawing: bool = False
        self.current_stroke_physical: List[Tuple[int, int]] = []
        self.current_stroke_logical: List[QPoint] = []
        self.completed_strokes_physical: List[List[Tuple[int, int]]] = []
        self.completed_strokes_logical: List[List[QPoint]] = []

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
        """Clear active rectangle and freehand strokes on this overlay."""
        self.start_pos = None
        self.current_pos = None
        self.is_dragging = False
        self.selection_rect = None

        self.is_drawing = False
        self.current_stroke_physical = []
        self.current_stroke_logical = []
        self.completed_strokes_physical = []
        self.completed_strokes_logical = []
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. Paint native frozen pixmap
        painter.drawPixmap(0, 0, self.captured.pixmap)

        # 2. Dimming & Selection Highlights based on active mode
        if self.manager.mode == "rectangle":
            self._paint_rectangle_mode(painter)
        else:
            self._paint_freehand_mode(painter)

        # 3. Top Hint Chip (shows active mode and shortcuts)
        self._paint_hint_chip(painter)

        painter.end()

    def _paint_rectangle_mode(self, painter: QPainter) -> None:
        """Render selection box and dimming for Rectangle mode."""
        if not self.selection_rect or self.selection_rect.isEmpty():
            painter.fillRect(self.rect(), COLOR_DIM)
        else:
            outside_region = QRegion(self.rect()).subtracted(QRegion(self.selection_rect))
            painter.setClipRegion(outside_region)
            painter.fillRect(self.rect(), COLOR_DIM)
            painter.setClipping(False)

            # Inside selection: light tint + 2px border
            painter.fillRect(self.selection_rect, COLOR_TINT)

            pen = QPen(COLOR_BORDER, BORDER_WIDTH)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            painter.drawRect(self.selection_rect.adjusted(0, 0, -1, -1))

            # Dimension label
            self._paint_pill_label(painter, self.selection_rect)

    def _paint_freehand_mode(self, painter: QPainter) -> None:
        """Render freehand strokes, fills, and dimming."""
        # Build union region of all completed strokes
        union_region = QRegion()
        for stroke_pts in self.completed_strokes_logical:
            if len(stroke_pts) >= 3:
                union_region = union_region.united(QRegion(QPolygon(stroke_pts)))

        # Dimming outside selection
        if union_region.isEmpty():
            painter.fillRect(self.rect(), COLOR_DIM)
        else:
            outside_region = QRegion(self.rect()).subtracted(union_region)
            painter.setClipRegion(outside_region)
            painter.fillRect(self.rect(), COLOR_DIM)
            painter.setClipping(False)

        # Paint completed strokes (filled tint + smooth 3px pink border with round caps and joins)
        pen = QPen(
            COLOR_BORDER,
            3,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setPen(pen)
        painter.setBrush(COLOR_TINT)

        for stroke_pts in self.completed_strokes_logical:
            if len(stroke_pts) >= 3:
                path = QPainterPath()
                path.addPolygon(QPolygon(stroke_pts))
                path.closeSubpath()
                painter.drawPath(path)

        # Paint active in-progress stroke (smooth line only, no fill yet)
        if len(self.current_stroke_logical) >= 2:
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(self.current_stroke_logical[0])
            for pt in self.current_stroke_logical[1:]:
                path.lineTo(pt)
            painter.drawPath(path)

        # Paint dimension label for bounding box of completed strokes
        all_physical = []
        for s in self.completed_strokes_physical:
            all_physical.extend(s)

        if all_physical:
            _, _, bw, bh = polygon_bounding_box(all_physical)
            if bw > 0 and bh > 0:
                all_logical = []
                for s in self.completed_strokes_logical:
                    all_logical.extend(s)
                xs = [p.x() for p in all_logical]
                ys = [p.y() for p in all_logical]
                bounding_rect = QRect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
                self._paint_pill_label(painter, bounding_rect, physical_size=(bw, bh))

    def _paint_pill_label(
        self,
        painter: QPainter,
        rect: QRect,
        physical_size: Optional[Tuple[int, int]] = None,
    ) -> None:
        """Draw a pill badge showing width x height in physical pixels."""
        if physical_size is not None:
            pw, ph = physical_size
        else:
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

        x = rect.center().x() - pill_w // 2
        y = rect.bottom() + 8
        if y + pill_h > self.height() - 8:
            y = rect.top() - pill_h - 8

        x = max(8, min(x, self.width() - pill_w - 8))
        y = max(8, min(y, self.height() - pill_h - 8))

        pill_rect = QRect(x, y, pill_w, pill_h)

        painter.setBrush(COLOR_PILL_BG)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(pill_rect, 5, 5)

        painter.setPen(COLOR_PILL_TEXT)
        painter.drawText(pill_rect, Qt.AlignmentFlag.AlignCenter, label_text)

    def _paint_hint_chip(self, painter: QPainter) -> None:
        """Draw top centered hint badge showing mode and keyboard controls."""
        hint_text = (
            "Freehand: draw around what you want. Esc cancel, Tab switch mode, Backspace clear."
            if self.manager.mode == "freehand"
            else "Rectangle: drag to select a rectangle. Esc cancel, Tab switch mode, Backspace clear."
        )

        font = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(hint_text)
        text_h = fm.height()

        chip_w = text_w + 24
        chip_h = text_h + 10
        chip_x = (self.width() - chip_w) // 2
        chip_y = 16

        chip_rect = QRect(chip_x, chip_y, chip_w, chip_h)

        painter.setBrush(COLOR_PILL_BG)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(chip_rect, 6, 6)

        painter.setPen(COLOR_PILL_TEXT)
        painter.drawText(chip_rect, Qt.AlignmentFlag.AlignCenter, hint_text)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.manager.notify_activity()

        if event.button() == Qt.MouseButton.RightButton:
            self.manager.cancel()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.manager.clear_other_selections(self)

            pos = event.position().toPoint()
            cur_x = max(0, min(pos.x(), self.width()))
            cur_y = max(0, min(pos.y(), self.height()))
            clamped_pos = QPoint(cur_x, cur_y)

            if self.manager.mode == "rectangle":
                self.start_pos = clamped_pos
                self.current_pos = clamped_pos
                self.is_dragging = True
                self.selection_rect = None
                self.update()
            else:  # Freehand
                self.is_drawing = True
                dpr = self.captured.dpr
                px = round(cur_x * dpr)
                py = round(cur_y * dpr)
                self.current_stroke_physical = [(px, py)]
                self.current_stroke_logical = [clamped_pos]
                self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.manager.notify_activity()

        pos = event.position().toPoint()
        cur_x = max(0, min(pos.x(), self.width()))
        cur_y = max(0, min(pos.y(), self.height()))

        if self.manager.mode == "rectangle":
            if self.is_dragging and self.start_pos is not None:
                self.current_pos = QPoint(cur_x, cur_y)
                x, y, w, h = normalize_rect(
                    self.start_pos.x(),
                    self.start_pos.y(),
                    self.current_pos.x(),
                    self.current_pos.y(),
                )
                self.selection_rect = QRect(x, y, w, h)
                self.update()
        else:  # Freehand
            if self.is_drawing and self.current_stroke_logical:
                dpr = self.captured.dpr
                px = round(cur_x * dpr)
                py = round(cur_y * dpr)
                if add_point_if_far_enough(self.current_stroke_physical, (px, py), min_distance=2.0):
                    last_pt = self.current_stroke_logical[-1]
                    new_pt = QPoint(cur_x, cur_y)
                    self.current_stroke_logical.append(new_pt)

                    # Performance: Repaint only the dirty rectangle between last_pt and new_pt
                    min_lx = min(last_pt.x(), new_pt.x()) - 6
                    min_ly = min(last_pt.y(), new_pt.y()) - 6
                    dirty_w = abs(new_pt.x() - last_pt.x()) + 12
                    dirty_h = abs(new_pt.y() - last_pt.y()) + 12
                    self.update(QRect(min_lx, min_ly, dirty_w, dirty_h))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self.manager.notify_activity()

        if event.button() == Qt.MouseButton.LeftButton:
            if self.manager.mode == "rectangle":
                if self.is_dragging:
                    self.is_dragging = False
                    if self.selection_rect:
                        pw = round(self.selection_rect.width() * self.captured.dpr)
                        ph = round(self.selection_rect.height() * self.captured.dpr)

                        if is_valid_selection(pw, ph, MIN_SELECTION_PIXELS, MIN_SELECTION_PIXELS):
                            self.manager.confirm_selection(self, self.selection_rect)
                        else:
                            self.clear_selection()
            else:  # Freehand
                if self.is_drawing:
                    self.is_drawing = False
                    stroke_pts = self.current_stroke_physical
                    self.current_stroke_physical = []
                    self.current_stroke_logical = []

                    # Degenerate input check: single click, straight line, bbox < 8x8, area < 64
                    if is_degenerate_stroke(stroke_pts, min_w=8, min_h=8, min_area=64.0):
                        self.update()
                        return

                    # Close path automatically
                    closed_physical = close_path(stroke_pts)
                    dpr = self.captured.dpr
                    closed_logical = [
                        QPoint(round(px / dpr), round(py / dpr))
                        for (px, py) in closed_physical
                    ]

                    shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                    if shift_held:
                        # Add another stroke: selection stays open
                        self.completed_strokes_physical.append(closed_physical)
                        self.completed_strokes_logical.append(closed_logical)
                        self.update()
                    else:
                        # Confirm single stroke immediately
                        self.completed_strokes_physical.append(closed_physical)
                        self.completed_strokes_logical.append(closed_logical)
                        self.update()
                        self.manager.confirm_freehand_selection(
                            self, self.completed_strokes_physical
                        )

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        self.manager.notify_activity()
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self.manager.cancel()
        elif key == Qt.Key.Key_Tab:
            self.manager.toggle_mode()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.manager.mode == "rectangle":
                if self.selection_rect:
                    pw = round(self.selection_rect.width() * self.captured.dpr)
                    ph = round(self.selection_rect.height() * self.captured.dpr)
                    if is_valid_selection(pw, ph, MIN_SELECTION_PIXELS, MIN_SELECTION_PIXELS):
                        self.manager.confirm_selection(self, self.selection_rect)
            else:  # Freehand
                if self.completed_strokes_physical:
                    self.manager.confirm_freehand_selection(
                        self, self.completed_strokes_physical
                    )
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
        self.mode: str = "freehand"  # "freehand" (default) or "rectangle"
        self.outside_shape: str = "blank"  # "blank" (default) or "keep"

        # Safety timeout: cancel if inactive for 60 seconds
        self.safety_timer = QTimer(self)
        self.safety_timer.setSingleShot(True)
        self.safety_timer.timeout.connect(self._on_timeout)

        # Monitor topology change listener (cancel safely if monitor plugged/unplugged)
        app = QGuiApplication.instance()
        if app:
            app.screenAdded.connect(self._on_screens_changed)
            app.screenRemoved.connect(self._on_screens_changed)

    def set_mode(self, mode: str) -> None:
        """Set active selection mode ('freehand' or 'rectangle') across all overlays."""
        if mode not in ("freehand", "rectangle"):
            mode = "freehand"
        self.mode = mode
        for ov in self.overlays:
            ov.clear_selection()
        logger.info("Overlay mode switched to: %s", self.mode)

    def toggle_mode(self) -> None:
        """Toggle mode between freehand and rectangle."""
        new_mode = "rectangle" if self.mode == "freehand" else "freehand"
        self.set_mode(new_mode)

    def _on_screens_changed(self, *args) -> None:
        if self.overlays:
            logger.info("Screen topology changed during selection. Cancelling selection safely.")
            self.cancel()

    def start_selection(
        self,
        captured_monitors: List[CapturedMonitor],
        foreground_hwnd: int = 0,
        mode: Optional[str] = None,
        outside_shape: Optional[str] = None,
    ) -> None:
        """Display frozen overlays on all monitors and begin selection."""
        self.cleanup()
        self.saved_foreground_hwnd = foreground_hwnd
        if mode:
            self.mode = mode
        if outside_shape:
            self.outside_shape = outside_shape

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

            if mon.logical_geometry.contains(cursor_pos):
                focused_overlay = overlay

        # Ensure active monitor gets keyboard focus immediately
        target_overlay = focused_overlay or (self.overlays[0] if self.overlays else None)
        if target_overlay is not None:
            target_overlay.activateWindow()
            win32.set_foreground_window(target_overlay.winId())

        # Start 60s safety timeout
        self.notify_activity()
        logger.info(
            "Selection overlays displayed across %d monitor(s) (mode=%s, outside_shape=%s)",
            len(self.overlays),
            self.mode,
            self.outside_shape,
        )

    def notify_activity(self) -> None:
        """Reset the 60s inactivity safety timer."""
        self.safety_timer.start(60_000)

    def _on_timeout(self) -> None:
        logger.info("Selection cancelled due to 60s inactivity safety timeout.")
        self.cancel()

    def clear_other_selections(self, active_overlay: SelectionOverlay) -> None:
        """Ensure only one monitor has an active selection."""
        for ov in self.overlays:
            if ov is not active_overlay:
                ov.clear_selection()

    def confirm_selection(self, overlay: SelectionOverlay, logical_rect: QRect) -> None:
        """Extract cropped physical QImage for Rectangle mode and clean up overlays."""
        self.safety_timer.stop()

        dpr = overlay.captured.dpr
        px = round(logical_rect.x() * dpr)
        py = round(logical_rect.y() * dpr)
        pw = round(logical_rect.width() * dpr)
        ph = round(logical_rect.height() * dpr)

        cropped_img = extract_crop(overlay.captured.image, (px, py, pw, ph))
        logger.info("Rectangle crop confirmed: %d x %d physical px (DPR %.2f)", pw, ph, dpr)

        global_origin = overlay.geometry().topLeft()
        self.last_selection_rect = QRect(global_origin + logical_rect.topLeft(), logical_rect.size())
        self.last_screen = overlay.captured.screen

        self.cleanup()
        self.crop_confirmed.emit(cropped_img)

    def confirm_freehand_selection(
        self,
        overlay: SelectionOverlay,
        strokes_physical: List[List[Tuple[int, int]]],
    ) -> None:
        """Extract cropped physical QImage for Freehand mode and clean up overlays."""
        self.safety_timer.stop()

        if not strokes_physical:
            logger.warning("confirm_freehand_selection called with empty strokes.")
            return

        cropped_img = crop_freehand(
            overlay.captured.image,
            strokes_physical,
            outside_shape=self.outside_shape,
        )

        boxes = [polygon_bounding_box(s) for s in strokes_physical]
        ux, uy, uw, uh = union_bounding_boxes(boxes)

        dpr = overlay.captured.dpr
        logical_x = round(ux / dpr)
        logical_y = round(uy / dpr)
        logical_w = round(uw / dpr)
        logical_h = round(uh / dpr)

        logger.info(
            "Freehand crop confirmed: %d x %d physical px (outside_shape=%s)",
            uw,
            uh,
            self.outside_shape,
        )

        global_origin = overlay.geometry().topLeft()
        self.last_selection_rect = QRect(
            global_origin + QPoint(logical_x, logical_y),
            QSize(logical_w, logical_h),
        )
        self.last_screen = overlay.captured.screen

        self.cleanup()
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

