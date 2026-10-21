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

PEACHY_HOTKEY_ID = 0x5045  # "PE" in ASCII

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

    def __init__(self, hotkey_id: int, on_hotkey: callable):
        super().__init__()
        self._hotkey_id = hotkey_id
        self._on_hotkey = on_hotkey

    def nativeEventFilter(self, event_type, message):
        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == win32.WM_HOTKEY:
                if msg.wParam == self._hotkey_id:
                    self._on_hotkey()
                    return True, 0
        except Exception as exc:
            logger.debug("Error in nativeEventFilter: %s", exc)
        return False, 0


class HotkeyManager(QObject):
    """Manages system-wide hotkey registration and notification."""

    hotkey_triggered = Signal()
    registration_failed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None, hotkey_id: int = PEACHY_HOTKEY_ID):
        super().__init__(parent)
        self._hotkey_id = hotkey_id
        self._current_shortcut: Optional[str] = None
        self._modifiers = 0
        self._vk = 0
        self._is_registered = False
        self._is_paused = False

        self._filter = _WinHotkeyEventFilter(self._hotkey_id, self._handle_hotkey)
        app = QCoreApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._filter)

    @property
    def is_registered(self) -> bool:
        return self._is_registered

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def current_shortcut(self) -> Optional[str]:
        return self._current_shortcut

    def _handle_hotkey(self) -> None:
        """Internal callback invoked by the native event filter."""
        if self._is_paused:
            logger.debug("Hotkey received but manager is paused.")
            return
        logger.info("Global hotkey triggered.")
        self.hotkey_triggered.emit()

    def register(self, shortcut_str: str) -> bool:
        """Register a new global hotkey.

        Unregisters any previous hotkey first.
        If registration fails (e.g. key in use), emits registration_failed and keeps running.
        """
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
            # Kept for when unpaused
            return True

        success = win32.register_hotkey(None, self._hotkey_id, self._modifiers, self._vk)
        if success:
            self._is_registered = True
            logger.info("Successfully registered global hotkey: %s", shortcut_str)
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
        """Unregister the currently active hotkey."""
        if not self._is_registered:
            return True

        success = win32.unregister_hotkey(None, self._hotkey_id)
        self._is_registered = False
        logger.info("Unregistered hotkey: %s", self._current_shortcut)
        return success

    def set_paused(self, paused: bool) -> None:
        """Pause or unpause hotkey interception."""
        if self._is_paused == paused:
            return

        self._is_paused = paused
        if paused:
            if self._is_registered:
                win32.unregister_hotkey(None, self._hotkey_id)
                self._is_registered = False
                logger.info("Paused hotkey %s (unregistered from OS)", self._current_shortcut)
        else:
            if self._current_shortcut:
                logger.info("Resuming hotkey %s", self._current_shortcut)
                self.register(self._current_shortcut)

    def cleanup(self) -> None:
        """Cleanly unregister and remove native event filter upon application shutdown."""
        self.unregister()
        app = QCoreApplication.instance()
        if app is not None and self._filter is not None:
            app.removeNativeEventFilter(self._filter)
            self._filter = None
