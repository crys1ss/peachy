"""Low-level Windows keyboard hook for double-tap C detection.

Features:
- Pure DoubleTapDetector class for unit-testing key state transitions.
- Low-level WH_KEYBOARD_LL hook callback via ctypes returning within a few ms.
- Rejects injected events (LLKHF_INJECTED) and auto-repeat from held keys.
- Requires plain 'C' without Ctrl, Alt, or Win modifiers.
- Strictly unswallows all events (always calls CallNextHookEx).
- Documented UIPI limitation for elevated (Administrator) windows.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal

from core import win32

logger = logging.getLogger(__name__)


class DoubleTapDetector:
    """Pure logic class for detecting double-tap C events with precise timing and guards."""

    def __init__(self, interval_ms: int = 280):
        self.interval_ms = interval_ms
        self._last_c_down_time: Optional[float] = None
        self._c_is_physically_down: bool = False

    def set_interval(self, interval_ms: int) -> None:
        """Update double-tap window (clamped between 200 and 500 ms)."""
        self.interval_ms = max(200, min(500, interval_ms))

    def reset(self) -> None:
        """Reset internal detection state."""
        self._last_c_down_time = None
        self._c_is_physically_down = False

    def process_key(
        self,
        vk_code: int,
        is_down: bool,
        is_injected: bool = False,
        ctrl_down: bool = False,
        alt_down: bool = False,
        win_down: bool = False,
        timestamp: Optional[float] = None,
    ) -> bool:
        """Process a key event and return True if a valid double-tap C fired.

        Rules:
        - Injected events (LLKHF_INJECTED) are ignored.
        - Physical state of 'C' tracks auto-repeat (if already held down, repeated down events are ignored).
        - Modifiers (Ctrl, Alt, Win) cancel any active double-tap sequence.
        - Any non-C key down event cancels the active sequence.
        - Exactly two consecutive plain C key-downs within interval_ms fire the trigger.
        """
        # Rule: Ignore injected events
        if is_injected:
            return False

        current_time = timestamp if timestamp is not None else time.monotonic()

        # Handle key releases (up events)
        if not is_down:
            if vk_code == win32.VK_C:
                self._c_is_physically_down = False
            return False

        # Key DOWN event:
        # Rule: Count only plain C with no Ctrl, Alt, or Win held
        if ctrl_down or alt_down or win_down:
            self._last_c_down_time = None
            if vk_code == win32.VK_C:
                self._c_is_physically_down = True
            return False

        # If this is the 'C' key
        if vk_code == win32.VK_C:
            # Rule: Ignore auto-repeat from a held key
            if self._c_is_physically_down:
                return False

            self._c_is_physically_down = True

            # Check if this is the second tap of a valid sequence
            if self._last_c_down_time is not None:
                elapsed_ms = (current_time - self._last_c_down_time) * 1000.0
                if 0 <= elapsed_ms <= self.interval_ms:
                    # Valid double tap!
                    self._last_c_down_time = None
                    return True
                else:
                    # Interval expired, treat as first tap of a new sequence
                    self._last_c_down_time = current_time
                    return False
            else:
                # First tap recorded
                self._last_c_down_time = current_time
                return False

        # Rule: Any other key down between taps cancels the sequence
        self._last_c_down_time = None
        return False


class DoubleTapHook(QObject):
    """Windows low-level keyboard hook (WH_KEYBOARD_LL) for double-tap C activation.

    IMPORTANT NOTE ON ADMIN WINDOWS (UIPI):
    Under Windows User Interface Privilege Isolation (UIPI), a standard non-elevated
    process cannot monitor keyboard messages directed toward elevated (Run as Administrator)
    windows unless Peachy itself is launched with Administrator privileges.
    """

    triggered = Signal()

    def __init__(self, interval_ms: int = 280, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.detector = DoubleTapDetector(interval_ms)
        self._hook_handle: Optional[int] = None
        self._is_enabled: bool = False
        self._is_paused: bool = False

        # Rule: Keep a strong reference to the callback so Python never garbage-collects it
        self._hook_proc = win32.HOOKPROC(self._low_level_proc)

    def is_installed(self) -> bool:
        """Return True if hook is currently active in the Windows hook chain."""
        return self._hook_handle is not None

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the double-tap hook."""
        self._is_enabled = enabled
        if self._is_enabled and not self._is_paused:
            self.install()
        else:
            self.uninstall()

    def set_paused(self, paused: bool) -> None:
        """Pause or unpause hook interception (e.g. from system tray toggle)."""
        self._is_paused = paused
        if self._is_enabled and not self._is_paused:
            self.install()
        else:
            self.uninstall()

    def set_interval(self, interval_ms: int) -> None:
        """Update detection interval in milliseconds."""
        self.detector.set_interval(interval_ms)

    def install(self) -> bool:
        """Install WH_KEYBOARD_LL hook."""
        if self._hook_handle is not None:
            return True  # Already installed

        handle = win32.set_windows_hook(win32.WH_KEYBOARD_LL, self._hook_proc)
        if handle:
            self._hook_handle = handle
            logger.info("DoubleTapHook installed (handle=%d)", handle)
            return True
        else:
            logger.warning("Failed to install WH_KEYBOARD_LL hook.")
            return False

    def uninstall(self) -> None:
        """Remove WH_KEYBOARD_LL hook."""
        if self._hook_handle is not None:
            win32.unhook_windows_hook(self._hook_handle)
            logger.info("DoubleTapHook uninstalled (handle=%d)", self._hook_handle)
            self._hook_handle = None
        self.detector.reset()

    def _low_level_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        """Fast low-level keyboard callback.

        Rules:
        - Return within a few milliseconds
        - Never swallow or alter key events
        - Always call CallNextHookEx
        """
        if n_code >= 0 and l_param:
            try:
                kbd = win32.KBDLLHOOKSTRUCT.from_address(l_param)
                vk = kbd.vkCode
                flags = kbd.flags
                is_injected = bool(flags & win32.LLKHF_INJECTED)
                is_down = (w_param in (win32.WM_KEYDOWN, win32.WM_SYSKEYDOWN))

                # Check modifier keys
                ctrl_down = win32.is_key_down(win32.VK_CONTROL)
                alt_down = win32.is_key_down(win32.VK_MENU)
                win_down = win32.is_key_down(win32.VK_LWIN) or win32.is_key_down(win32.VK_RWIN)

                fired = self.detector.process_key(
                    vk_code=vk,
                    is_down=is_down,
                    is_injected=is_injected,
                    ctrl_down=ctrl_down,
                    alt_down=alt_down,
                    win_down=win_down,
                )
                if fired:
                    # Post Qt signal
                    self.triggered.emit()
            except Exception as exc:
                logger.error("Exception in low-level keyboard hook callback: %s", exc)

        return win32.call_next_hook(self._hook_handle, n_code, w_param, l_param)
