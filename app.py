"""Peachy - Desktop Screen Assistant.

Application entry point featuring:
- Single-instance guard (signals active instance and exits if already running)
- Secure rotated logging to %LOCALAPPDATA%\\Peachy\\logs with privacy redaction
- System tray residence (setQuitOnLastWindowClosed(False))
- Global hotkey listener and finite state machine integration
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
from typing import Optional

from PySide6.QtCore import QObject, QtMsgType, qInstallMessageHandler
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from capture.screen_capture import capture_all_monitors
from capture.selection_overlay import OverlayManager
from config.settings import Settings, load_settings
from core import win32
from core.app_controller import AppController
from core.double_tap import DoubleTapHook
from core.hotkey_manager import HotkeyManager
from core.state_manager import AppState, StateManager
from ui.peachy_popup import PeachyPopup
from ui.history_window import HistoryWindow
from ui.settings_window import SettingsWindow
from ui.tray_manager import TrayManager
from history.store import HistoryStore
from ui.sound import get_sound_manager

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


def setup_resilient_error_handling(app_coordinator: Optional[PeachyApp] = None) -> None:
    """Install sys.excepthook and Qt message handler to prevent crashes and log safely."""

    def excepthook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logging.critical(
            "Unhandled exception caught by global excepthook:",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

        if app_coordinator is not None:
            try:
                app_coordinator.tray_manager.show_notification(
                    "Peachy Recovered",
                    "An unexpected error occurred and was safely logged.",
                )
                app_coordinator.state_manager.reset_to_idle()
                if hasattr(app_coordinator, "popup") and app_coordinator.popup:
                    app_coordinator.popup.hide()
                if hasattr(app_coordinator, "overlay_manager") and app_coordinator.overlay_manager:
                    app_coordinator.overlay_manager.cleanup()
            except Exception as rec_err:
                logging.error("Error during excepthook recovery: %s", rec_err)

    sys.excepthook = excepthook

    def qt_message_handler(mode, context, message):
        # Ignore benign Windows geometry adjustments
        if "QWindowsWindow::setGeometry" in message:
            return
        if mode == QtMsgType.QtDebugMsg:
            logging.debug("Qt: %s", message)
        elif mode == QtMsgType.QtInfoMsg:
            logging.info("Qt: %s", message)
        elif mode == QtMsgType.QtWarningMsg:
            logging.warning("Qt: %s", message)
        elif mode == QtMsgType.QtCriticalMsg:
            logging.error("Qt: %s", message)
        elif mode == QtMsgType.QtFatalMsg:
            logging.critical("Qt Fatal: %s", message)

    qInstallMessageHandler(qt_message_handler)


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
        self.sound_manager = get_sound_manager(self.settings)

        # 3. System Tray
        self.tray_manager = TrayManager(self)

        # 4. Hotkey Manager
        self.hotkey_manager = HotkeyManager(self)

        # 5. Double-Tap C Hook (optional low-level WH_KEYBOARD_LL hook)
        self.double_tap_hook = DoubleTapHook(
            interval_ms=self.settings.double_tap_interval_ms,
            parent=self,
        )

        # 6. Screen Capture Overlay Coordinator
        self.overlay_manager = OverlayManager()

        # 7. Peachy Popup Window
        self.popup = PeachyPopup(
            pinned=self.settings.pinned,
            answer_length=self.settings.answer_length,
            settings=self.settings,
        )

        # 8. Chat History Store & Window
        self.history_store = HistoryStore()
        self.history_window = HistoryWindow(store=self.history_store, settings=self.settings)

        # 9. App Controller
        self.controller = AppController(
            state_manager=self.state_manager,
            hotkey_manager=self.hotkey_manager,
            tray_manager=self.tray_manager,
            overlay_manager=self.overlay_manager,
            popup=self.popup,
            settings=self.settings,
            history_store=self.history_store,
            history_window=self.history_window,
            parent=self,
        )

        # 10. Settings Window
        self.settings_window = SettingsWindow(
            settings=self.settings,
            hotkey_manager=self.hotkey_manager,
            double_tap_hook=self.double_tap_hook,
            store=self.history_store,
        )

        self._connect_signals()

        # Register configured hotkey
        reg_ok = self.hotkey_manager.register(self.settings.hotkey)
        if not reg_ok:
            self.tray_manager.show_notification(
                "Hotkey Warning",
                f"Could not register shortcut '{self.settings.hotkey}'. It may be in use.",
            )

        # Register configured history hotkey
        if self.settings.history_hotkey:
            reg_hist_ok = self.hotkey_manager.register_history(self.settings.history_hotkey)
            if not reg_hist_ok:
                self.tray_manager.show_notification(
                    "History Hotkey Warning",
                    f"Could not register history shortcut '{self.settings.history_hotkey}'. It may be in use.",
                )

        # Enable double-tap C if configured
        if self.settings.double_tap_enabled:
            self.double_tap_hook.set_enabled(True)

        # Show tray icon
        self.tray_manager.show()
        self.logger.info("Peachy started. Hotkey: %s", self.settings.hotkey)

    def _connect_signals(self) -> None:
        """Wire UI, Hotkey, Hook, and State Machine signals."""
        self.hotkey_manager.registration_failed.connect(
            lambda msg: self.tray_manager.show_notification("Hotkey Conflict", msg)
        )
        self.hotkey_manager.history_registration_failed.connect(
            lambda msg: self.tray_manager.show_notification("Hotkey Conflict", msg)
        )

        # Double-tap C trigger
        self.double_tap_hook.triggered.connect(self.on_activated)

        # Tray signals
        self.tray_manager.settings_requested.connect(self.open_settings)
        self.tray_manager.pause_toggled.connect(self._on_pause_toggled)
        self.tray_manager.quit_requested.connect(self.quit)

        # Settings window applied
        self.settings_window.settings_applied.connect(self._on_settings_applied)

        # Incoming single-instance IPC connections
        self.server.newConnection.connect(self._handle_ipc_connection)

    def _on_pause_toggled(self, paused: bool) -> None:
        """Pause or resume both hotkeys and double-tap hook."""
        self.hotkey_manager.set_paused(paused)
        self.double_tap_hook.set_paused(paused)

    def _on_settings_applied(self, new_settings: Settings) -> None:
        """Update active settings across all running components."""
        try:
            old_history_hotkey = self.settings.history_hotkey
            old_hotkey = self.settings.hotkey

            self.settings = new_settings
            self.controller.settings = new_settings
            get_sound_manager(new_settings)
            if hasattr(self, "history_window") and self.history_window:
                self.history_window.settings = new_settings
                self.history_window.apply_theme(
                    theme_mode=new_settings.theme,
                    accent=getattr(new_settings, "accent", "peach"),
                    font_scale=getattr(new_settings, "font_scale", 100),
                )
            if hasattr(self, "popup") and self.popup:
                self.popup.settings = new_settings
                if hasattr(self.popup, "apply_theme"):
                    self.popup.apply_theme(
                        theme_mode=new_settings.theme,
                        accent=getattr(new_settings, "accent", "peach"),
                        font_scale=getattr(new_settings, "font_scale", 100),
                    )
            if hasattr(self.popup, "set_pinned"):
                self.popup.set_pinned(new_settings.pinned)
            else:
                self.popup.pinned = new_settings.pinned
            if hasattr(self.popup, "set_answer_length"):
                self.popup.set_answer_length(new_settings.answer_length)
            if self.state_manager.state == AppState.ERROR:
                self.controller.on_popup_cancelled()

            # Re-register hotkeys if modified
            if new_settings.hotkey != old_hotkey:
                self.hotkey_manager.register(new_settings.hotkey)
            if new_settings.history_hotkey != old_history_hotkey:
                self.hotkey_manager.register_history(new_settings.history_hotkey)

            self.logger.info("Settings updated and applied live.")
        except Exception as exc:
            self.logger.exception("Error applying updated settings: %s", exc)

    def open_settings(self) -> None:
        """Display the settings window."""
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _handle_ipc_connection(self) -> None:
        """Handle IPC connection from a second launch attempt."""
        socket = self.server.nextPendingConnection()
        if socket:
            socket.waitForReadyRead(500)
            data = bytes(socket.readAll()).decode("utf-8", errors="ignore").strip()
            self.logger.info("Received IPC command from another instance: %s", data)
            if "open_settings" in data:
                self.open_settings()
                self.tray_manager.show_notification(
                    "Peachy is already running",
                    "Opened Settings from another launch attempt.",
                )
            socket.disconnectFromServer()

    def on_activated(self) -> None:
        """Delegate activation to controller."""
        self.controller.on_activated()

    def quit(self) -> None:
        """Clean shutdown handler."""
        self.logger.info("Shutting down Peachy...")
        self.double_tap_hook.uninstall()
        self.hotkey_manager.cleanup()
        self.controller.shutdown()
        self.overlay_manager.cleanup()
        self.tray_manager.hide()
        self.popup.close()
        if hasattr(self, "history_window") and self.history_window:
            self.history_window.close()
        self.settings_window.close()
        self.server.close()
        self.app.quit()


def check_single_instance() -> tuple[bool, QLocalServer | None]:
    """Ensure only one instance runs."""
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

    peachy_app = PeachyApp(app, server)
    setup_resilient_error_handling(peachy_app)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
