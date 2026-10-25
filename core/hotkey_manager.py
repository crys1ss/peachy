"""Global hotkey management for Windows using RegisterHotKey and QAbstractNativeEventFilter.

Parses human-readable shortcut strings (e.g., 'Ctrl+Shift+Space', 'Alt+Q')
and registers with Windows user32. Intercepts WM_HOTKEY in the Qt event loop.
"""

from __future__ import annotations

from ctypes import wintypes
import logging
from typing import Optional, Tuple

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

from core import win32

logger = logging.getLogger(__name__)

PEACHY_HOTKEY_ID = 0x5045  # "PE" in ASCII (Capture hotkey)
PEACHY_HISTORY_HOTKEY_ID = 0x5048  # "PH" in ASCII (History hotkey)

# Common Windows Virtual-Key Codes
_VK_MAP: dict[str, int] = {
    "SPACE": 0x20,
    "ENTER": 0x0D,
    "RETURN": 0x0D,
    "ESC": 0x1B,
    "ESCAPE": 0x1B,
    "TAB": 0x09,
    "BACKSPACE": 0x08,
    "DELETE": 0x2E,
    "DEL": 0x2E,
    "INSERT": 0x2D,
    "INS": 0x2D,
    "HOME": 0x24,
    "END": 0x23,
    "PAGEUP": 0x21,
    "PGUP": 0x21,
    "PAGEDOWN": 0x22,
    "PGDN": 0x22,
    "LEFT": 0x25,
    "UP": 0x26,
    "RIGHT": 0x27,
    "DOWN": 0x28,
    "PRINTSCREEN": 0x2C,
    "PRTSC": 0x2C,
    "PAUSE": 0x13,
}

# Function keys F1-F24 (0x70 to 0x87)
for _i in range(1, 25):
    _VK_MAP[f"F{_i}"] = 0x70 + (_i - 1)


def parse_shortcut(shortcut_str: str) -> Tuple[int, int]:
    """Parse a shortcut string like 'Ctrl+Shift+Space' into (modifiers, vk_code).

    Always includes MOD_NOREPEAT (0x4000) in modifiers.
    Raises ValueError on invalid shortcut string.
    """
    if not shortcut_str or not shortcut_str.strip():
        raise ValueError("Shortcut string cannot be empty.")

    tokens = [t.strip().upper() for t in shortcut_str.split("+") if t.strip()]
    if not tokens:
        raise ValueError("Invalid shortcut format.")

    modifiers = win32.MOD_NOREPEAT
    vk_code: Optional[int] = None

    for token in tokens:
        if token in ("CTRL", "CONTROL"):
            modifiers |= win32.MOD_CONTROL
        elif token == "SHIFT":
            modifiers |= win32.MOD_SHIFT
        elif token == "ALT":
            modifiers |= win32.MOD_ALT
        elif token in ("WIN", "WINDOWS", "SUPER", "META"):
            modifiers |= win32.MOD_WIN
        else:
            # Must be the primary non-modifier key
            if vk_code is not None:
                raise ValueError(
                    f"Shortcut cannot contain multiple non-modifier keys ('{token}' and existing)."
                )

            if token in _VK_MAP:
                vk_code = _VK_MAP[token]
            elif len(token) == 1 and token.isalnum():
                vk_code = ord(token)
            else:
                raise ValueError(f"Unknown or unsupported key token: '{token}'")

    if vk_code is None:
        raise ValueError(f"Shortcut '{shortcut_str}' must contain at least one non-modifier key.")

    return modifiers, vk_code


class _WinHotkeyEventFilter(QAbstractNativeEventFilter):
    """Native event filter to capture WM_HOTKEY events on Windows."""

    def __init__(self, manager_or_id: Any, on_hotkey: Optional[callable] = None):
        super().__init__()
        if isinstance(manager_or_id, int):
            self._manager = None
            self._hotkey_id = manager_or_id
            self._on_hotkey = on_hotkey
        else:
            self._manager = manager_or_id
            self._hotkey_id = getattr(manager_or_id, "_hotkey_id", PEACHY_HOTKEY_ID)
            self._on_hotkey = None

    def nativeEventFilter(self, event_type, message):
        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == win32.WM_HOTKEY:
                if self._manager is not None:
                    if msg.wParam == self._manager._hotkey_id:
                        self._manager._handle_hotkey()
                        return True, 0
                    elif msg.wParam == self._manager._history_hotkey_id:
                        self._manager._handle_history_hotkey()
                        return True, 0
                elif self._on_hotkey is not None and msg.wParam == self._hotkey_id:
                    self._on_hotkey()
                    return True, 0
        except Exception as exc:
            logger.debug("Error in nativeEventFilter: %s", exc)
        return False, 0


class HotkeyManager(QObject):
    """Manages system-wide hotkey registration and notification for capture and history."""

    hotkey_triggered = Signal()
    registration_failed = Signal(str)
    history_hotkey_triggered = Signal()
    history_registration_failed = Signal(str)

    def __init__(
        self,
        parent: Optional[QObject] = None,
        hotkey_id: int = PEACHY_HOTKEY_ID,
        history_hotkey_id: int = PEACHY_HISTORY_HOTKEY_ID,
    ):
        super().__init__(parent)
        self._hotkey_id = hotkey_id
        self._history_hotkey_id = history_hotkey_id

        # Capture hotkey state
        self._current_shortcut: Optional[str] = None
        self._modifiers = 0
        self._vk = 0
        self._is_registered = False

        # History hotkey state
        self._current_history_shortcut: Optional[str] = None
        self._history_modifiers = 0
        self._history_vk = 0
        self._is_history_registered = False

        self._is_paused = False

        self._filter = _WinHotkeyEventFilter(self)
        app = QCoreApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)

    @property
    def is_registered(self) -> bool:
        return self._is_registered

    @property
    def is_history_registered(self) -> bool:
        return self._is_history_registered

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def current_shortcut(self) -> Optional[str]:
        return self._current_shortcut

    @property
    def current_history_shortcut(self) -> Optional[str]:
        return self._current_history_shortcut

    def _handle_hotkey(self) -> None:
        """Internal callback invoked by the native event filter for capture."""
        if self._is_paused:
            logger.debug("Capture hotkey received but manager is paused.")
            return
        logger.info("Global capture hotkey triggered.")
        self.hotkey_triggered.emit()

    def _handle_history_hotkey(self) -> None:
        """Internal callback invoked by the native event filter for history."""
        if self._is_paused:
            logger.debug("History hotkey received but manager is paused.")
            return
        logger.info("Global history hotkey triggered.")
        self.history_hotkey_triggered.emit()

    def register(self, shortcut_str: str) -> bool:
        """Register the primary screen capture global hotkey."""
        try:
            modifiers, vk = parse_shortcut(shortcut_str)
        except ValueError as err:
            msg = f"Invalid shortcut '{shortcut_str}': {err}"
            logger.error(msg)
            self.registration_failed.emit(msg)
            return False

        if self._is_registered:
            self.unregister()

        self._current_shortcut = shortcut_str
        self._modifiers = modifiers
        self._vk = vk

        if self._is_paused:
            return True

        success = win32.register_hotkey(None, self._hotkey_id, self._modifiers, self._vk)
        if success:
            self._is_registered = True
            logger.info("Successfully registered global capture hotkey: %s", shortcut_str)
            return True
        else:
            self._is_registered = False
            err_msg = (
                f"Failed to register hotkey '{shortcut_str}'. "
                "The shortcut may already be in use by another application."
            )
            logger.warning(err_msg)
            self.registration_failed.emit(err_msg)
            return False

    def unregister(self) -> bool:
        """Unregister the currently active capture hotkey."""
        if not self._is_registered:
            return True

        success = win32.unregister_hotkey(None, self._hotkey_id)
        self._is_registered = False
        logger.info("Unregistered capture hotkey: %s", self._current_shortcut)
        return success

    def register_history(self, shortcut_str: str) -> bool:
        """Register the secondary History global hotkey."""
        try:
            modifiers, vk = parse_shortcut(shortcut_str)
        except ValueError as err:
            msg = f"Invalid history shortcut '{shortcut_str}': {err}"
            logger.error(msg)
            self.history_registration_failed.emit(msg)
            return False

        if self._is_history_registered:
            self.unregister_history()

        self._current_history_shortcut = shortcut_str
        self._history_modifiers = modifiers
        self._history_vk = vk

        if self._is_paused:
            return True

        success = win32.register_hotkey(None, self._history_hotkey_id, self._history_modifiers, self._history_vk)
        if success:
            self._is_history_registered = True
            logger.info("Successfully registered global history hotkey: %s", shortcut_str)
            return True
        else:
            self._is_history_registered = False
            err_msg = (
                f"Failed to register history hotkey '{shortcut_str}'. "
                "The shortcut may already be in use by another application."
            )
            logger.warning(err_msg)
            self.history_registration_failed.emit(err_msg)
            return False

    def unregister_history(self) -> bool:
        """Unregister the currently active history hotkey."""
        if not self._is_history_registered:
            return True

        success = win32.unregister_hotkey(None, self._history_hotkey_id)
        self._is_history_registered = False
        logger.info("Unregistered history hotkey: %s", self._current_history_shortcut)
        return success

    def set_paused(self, paused: bool) -> None:
        """Pause or unpause both hotkeys."""
        if self._is_paused == paused:
            return

        self._is_paused = paused
        if paused:
            if self._is_registered:
                win32.unregister_hotkey(None, self._hotkey_id)
                self._is_registered = False
                logger.info("Paused capture hotkey %s (unregistered from OS)", self._current_shortcut)
            if self._is_history_registered:
                win32.unregister_hotkey(None, self._history_hotkey_id)
                self._is_history_registered = False
                logger.info("Paused history hotkey %s (unregistered from OS)", self._current_history_shortcut)
        else:
            if self._current_shortcut:
                logger.info("Resuming capture hotkey %s", self._current_shortcut)
                self.register(self._current_shortcut)
            if self._current_history_shortcut:
                logger.info("Resuming history hotkey %s", self._current_history_shortcut)
                self.register_history(self._current_history_shortcut)

    def cleanup(self) -> None:
        """Cleanly unregister both hotkeys and remove native event filter upon application shutdown."""
        self.unregister()
        self.unregister_history()
        app = QCoreApplication.instance()
        if app is not None and self._filter is not None:
            app.removeNativeEventFilter(self._filter)
            self._filter = None
