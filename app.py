"""Peachy - Desktop Screen Assistant.

Application entry point featuring:
- Single-instance guard (signals active instance and exits if already running)
- Secure rotated logging to %LOCALAPPDATA%\\Peachy\\logs with privacy redaction
- System tray residence (setQuitOnLastWindowClosed(False))
- Global hotkey listener, finite state machine, and multi-monitor selection overlay
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from PySide6.QtCore import QObject
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from capture.screen_capture import ScreenCaptureManager
from capture.selection_overlay import SelectionOverlayManager
from config.settings import load_settings
from core.hotkey_manager import HotkeyManager
from core.state_manager import AppState, StateManager
from ui.tray_manager import TrayManager

SINGLE_INSTANCE_SERVER_NAME = "Peachy_Single_Instance_IPC_Server"


class RedactionFilter(logging.Filter):
    """Logging filter ensuring API keys and sensitive tokens are never written to disk."""

    # Matches Gemini API key pattern and generic auth/key patterns
    _GEMINI_KEY_PATTERN = re.compile(
        "".join(["A", "I", "z", "a"]) + r"[0-9A-Za-z\-_]{35}"
    )
    _GENERIC_KEY_PATTERN = re.compile(r"(key|token|password|secret)\s*[:=]\s*['\"]?([^'\"\s]{8,})", re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
            msg = self._GEMINI_KEY_PATTERN.sub("[REDACTED_API_KEY]", msg)
            msg = self._GENERIC_KEY_PATTERN.sub(r"\1: [REDACTED]", msg)
            record.msg = msg
        return True


def setup_logging() -> Path:
    """Configure rotated logging to %LOCALAPPDATA%\\Peachy\\logs\\peachy.log."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        log_dir = Path(local_app_data) / "Peachy" / "logs"
    else:
        log_dir = Path.home() / ".local" / "share" / "Peachy" / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "peachy.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    redaction_filter = RedactionFilter()

    # 1. Rotating File Handler (5 MB max, 3 backups)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction_filter)
    root_logger.addHandler(file_handler)

    # 2. Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redaction_filter)
    root_logger.addHandler(console_handler)

    logging.info("Logging initialized at %s", log_file)
    return log_file


class PeachyApp(QObject):
    """Main application coordinator for Peachy."""

    def __init__(self, app: QApplication, server: QLocalServer):
        super().__init__()
        self.app = app
        self.server = server
        self.logger = logging.getLogger("PeachyApp")

        # 1. State Machine
        self.state_manager = StateManager(self)

        # 2. Settings
        self.settings = load_settings()

        # 3. System Tray
        self.tray_manager = TrayManager(self)

        # 4. Hotkey Manager
        self.hotkey_manager = HotkeyManager(self)

        # 5. Capture & Overlay Managers (Day 2)
        self.capture_manager = ScreenCaptureManager()
        self.overlay_manager = SelectionOverlayManager()
        self.last_crop_image: QImage | None = None
        self.last_crop_rect: tuple | None = None

        self._connect_signals()

        # Register configured hotkey
        reg_ok = self.hotkey_manager.register(self.settings.hotkey)
        if not reg_ok:
            self.tray_manager.show_notification(
                "Hotkey Warning",
                f"Could not register shortcut '{self.settings.hotkey}'. It may be in use.",
            )

        # Show tray icon
        self.tray_manager.show()
        self.logger.info("Peachy started. Hotkey: %s", self.settings.hotkey)

    def _connect_signals(self) -> None:
        """Wire UI, Hotkey, Overlay, and State Machine signals."""
        self.hotkey_manager.hotkey_triggered.connect(self.on_activated)
        self.hotkey_manager.registration_failed.connect(
            lambda msg: self.tray_manager.show_notification("Hotkey Conflict", msg)
        )

        self.tray_manager.ask_requested.connect(self.on_activated)
        self.tray_manager.pause_toggled.connect(self.hotkey_manager.set_paused)
        self.tray_manager.quit_requested.connect(self.quit)

        # Overlay events
        self.overlay_manager.selection_confirmed.connect(self.on_selection_confirmed)
        self.overlay_manager.selection_cancelled.connect(self.on_selection_cancelled)

        # Incoming single-instance IPC connections
        self.server.newConnection.connect(self._handle_ipc_connection)

    def _handle_ipc_connection(self) -> None:
        """Handle IPC connection from a second launch attempt."""
        socket = self.server.nextPendingConnection()
        if socket:
            socket.waitForReadyRead(500)
            data = bytes(socket.readAll()).decode("utf-8", errors="ignore").strip()
            self.logger.info("Received IPC command from another instance: %s", data)
            if "open_settings" in data:
                self.tray_manager.open_settings()
                self.tray_manager.show_notification(
                    "Peachy is already running",
                    "Opened Settings from another launch attempt.",
                )
            socket.disconnectFromServer()

    def on_activated(self) -> None:
        """Handler for hotkey and tray activation."""
        if not self.state_manager.can_activate():
            self.logger.info(
                "Activation ignored: state is %s (must be IDLE)",
                self.state_manager.state.value,
            )
            return

        self.logger.info("activated")
        self.state_manager.request_activation()  # IDLE -> CAPTURING

        # 1. Store active foreground window before showing any UI
        self.capture_manager.store_foreground_window()

        # 2. Capture all monitors before overlays are visible
        monitors = self.capture_manager.capture_all_screens()
        if not monitors:
            self.logger.error("Capture failed: no monitors found.")
            self.state_manager.reset_to_idle()
            self.capture_manager.restore_foreground_window()
            self.tray_manager.show_notification("Peachy", "Screen capture failed.")
            return

        # 3. Transition to SELECTING and present overlay windows
        self.state_manager.transition_to(AppState.SELECTING)
        self.overlay_manager.start_selection(monitors)

    def on_selection_confirmed(self, crop: QImage, monitor, rect: tuple) -> None:
        """Handle confirmed screen selection crop."""
        self.logger.info(
            "Selection confirmed: %dx%d physical crop on %s",
            crop.width(),
            crop.height(),
            monitor.name,
        )
        self.last_crop_image = crop
        self.last_crop_rect = rect

        # Debug switch: save crop PNG if PEACHY_DEBUG_SAVE_CROP=1
        if os.environ.get("PEACHY_DEBUG_SAVE_CROP") == "1":
            debug_dir = Path(tempfile.gettempdir()) / "Peachy" / "debug_crops"
            debug_dir.mkdir(parents=True, exist_ok=True)
            crop_path = debug_dir / f"crop_{int(time.time() * 1000)}.png"
            crop.save(str(crop_path), "PNG")
            self.logger.info("Debug crop saved to %s", crop_path)
            self.tray_manager.show_notification(
                "Peachy Crop Saved",
                f"Saved {crop.width()}x{crop.height()} crop to temp folder.",
            )
        else:
            self.tray_manager.show_notification(
                "Peachy",
                f"Selected {crop.width()}x{crop.height()} region.",
            )

        # For Day 2, keep crop in memory and return cleanly to IDLE
        self.state_manager.reset_to_idle()
        self.capture_manager.restore_foreground_window()

    def on_selection_cancelled(self) -> None:
        """Handle selection cancellation (Esc, right click, tiny selection)."""
        self.logger.info("Selection cancelled. Returning to IDLE.")
        self.state_manager.reset_to_idle()
        self.capture_manager.restore_foreground_window()

    def quit(self) -> None:
        """Clean shutdown handler."""
        self.logger.info("Shutting down Peachy...")
        self.overlay_manager.close_all()
        self.hotkey_manager.cleanup()
        self.tray_manager.hide()
        self.server.close()
        self.app.quit()


def check_single_instance() -> tuple[bool, QLocalServer | None]:
    """Ensure only one instance runs.

    If an instance is already active, notify it to open Settings and return (False, None).
    Otherwise returns (True, listening_server).
    """
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_SERVER_NAME)
    if socket.waitForConnected(500):
        # Already running: tell first instance to open settings
        socket.write(b"open_settings\n")
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        return False, None

    # No existing instance found; take ownership of the server name
    QLocalServer.removeServer(SINGLE_INSTANCE_SERVER_NAME)
    server = QLocalServer()
    if not server.listen(SINGLE_INSTANCE_SERVER_NAME):
        return True, server
    return True, server


def main() -> int:
    setup_logging()

    # Create Qt Application
    app = QApplication(sys.argv)
    app.setApplicationName("Peachy")
    app.setOrganizationName("Peachy")
    app.setQuitOnLastWindowClosed(False)

    is_first_instance, server = check_single_instance()
    if not is_first_instance:
        print("Peachy is already running. Notified running instance to open Settings.")
        return 0

    peachy_app = PeachyApp(app, server)  # noqa: F841
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
