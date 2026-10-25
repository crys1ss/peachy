"""System tray icon and menu management for Peachy.

Features a custom painted sparkle icon, contextual menu, and system notification toasts.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, QPointF, Qt, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton, QSystemTrayIcon, QVBoxLayout

logger = logging.getLogger(__name__)


def create_sparkle_icon(size: int = 64) -> QIcon:
    """Generate a cute anti-aliased pink sparkle icon using QPainter."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # 4-point star path centered at (size/2, size/2)
    center = size / 2.0
    outer_radius = size * 0.44
    inner_radius = size * 0.14

    path = QPainterPath()
    # Top tip
    path.moveTo(center, center - outer_radius)
    # Top-right curve / inner point
    path.lineTo(center + inner_radius, center - inner_radius)
    # Right tip
    path.lineTo(center + outer_radius, center)
    # Bottom-right inner point
    path.lineTo(center + inner_radius, center + inner_radius)
    # Bottom tip
    path.lineTo(center, center + outer_radius)
    # Bottom-left inner point
    path.lineTo(center - inner_radius, center + inner_radius)
    # Left tip
    path.lineTo(center - outer_radius, center)
    # Top-left inner point
    path.lineTo(center - inner_radius, center - inner_radius)
    path.closeSubpath()

    # Fill main sparkle in pink (#F472B6)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor("#F472B6")))
    painter.drawPath(path)

    # Small accent sparkle / dot at top-right
    accent_x = center + outer_radius * 0.55
    accent_y = center - outer_radius * 0.55
    accent_radius = size * 0.07
    painter.setBrush(QBrush(QColor("#EC4899")))
    painter.drawEllipse(QPointF(accent_x, accent_y), accent_radius, accent_radius)

    painter.end()
    return QIcon(pixmap)


class TrayManager(QObject):
    """Manages the system tray icon, context menu, and notifications."""

    ask_requested = Signal()
    history_requested = Signal()
    settings_requested = Signal()
    pause_toggled = Signal(bool)
    quit_requested = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._icon = create_sparkle_icon()
        self._tray_icon = QSystemTrayIcon(self._icon, parent)
        self._tray_icon.setToolTip("Peachy - Screen Assistant")

        self._menu = None
        self._pause_action: Optional[QAction] = None

        self._build_menu()
        self._tray_icon.activated.connect(self._on_tray_activated)

    def _build_menu(self) -> None:
        """Construct the contextual tray menu."""
        from PySide6.QtWidgets import QMenu

        self._menu = QMenu()

        ask_action = self._menu.addAction("Ask Peachy")
        ask_action.triggered.connect(self.ask_requested.emit)

        history_action = self._menu.addAction("History")
        history_action.triggered.connect(self.history_requested.emit)

        self._menu.addSeparator()

        settings_action = self._menu.addAction("Settings")
        settings_action.triggered.connect(self.open_settings)

        self._pause_action = self._menu.addAction("Pause Hotkey")
        self._pause_action.setCheckable(True)
        self._pause_action.setChecked(False)
        self._pause_action.toggled.connect(self.pause_toggled.emit)

        self._menu.addSeparator()

        quit_action = self._menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_requested.emit)

        self._tray_icon.setContextMenu(self._menu)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle clicks on the tray icon."""
        if reason == QSystemTrayIcon.Trigger:  # Single primary click
            self.ask_requested.emit()
        elif reason == QSystemTrayIcon.DoubleClick:
            self.open_settings()

    def show(self) -> None:
        """Display the tray icon."""
        self._tray_icon.show()

    def hide(self) -> None:
        """Hide the tray icon."""
        self._tray_icon.hide()

    def set_paused(self, paused: bool) -> None:
        """Update the pause menu item check state."""
        if self._pause_action is not None and self._pause_action.isChecked() != paused:
            self._pause_action.setChecked(paused)

    def open_settings(self) -> None:
        """Request the main application to display the visual settings window."""
        self.settings_requested.emit()

    def show_notification(self, title: str, message: str, msecs: int = 3000) -> None:
        """Show a system tray notification toast."""
        if self._tray_icon.isSystemTrayAvailable():
            self._tray_icon.showMessage(
                title,
                message,
                QSystemTrayIcon.MessageIcon.Information,
                msecs,
            )
        else:
            logger.info("Tray notification [%s]: %s", title, message)
