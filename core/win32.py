"""Win32 ctypes wrappers with strict typing and error checks.

All Win32 API interactions in Peachy are centralized here.
References:
- RegisterHotKey: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey
- UnregisterHotKey: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-unregisterhotkey
- GetForegroundWindow: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getforegroundwindow
- SetForegroundWindow: https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Load user32.dll
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

# Win32 Constants for Hotkeys
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312

# Common Win32 Error Codes
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

# Configure ctypes function signatures
# BOOL RegisterHotKey(HWND hWnd, int id, UINT fsModifiers, UINT vk);
_user32.RegisterHotKey.argtypes = [
    wintypes.HWND,
    ctypes.c_int,
    wintypes.UINT,
    wintypes.UINT,
]
_user32.RegisterHotKey.restype = wintypes.BOOL

# BOOL UnregisterHotKey(HWND hWnd, int id);
_user32.UnregisterHotKey.argtypes = [
    wintypes.HWND,
    ctypes.c_int,
]
_user32.UnregisterHotKey.restype = wintypes.BOOL

# HWND GetForegroundWindow(void);
_user32.GetForegroundWindow.argtypes = []
_user32.GetForegroundWindow.restype = wintypes.HWND

# BOOL SetForegroundWindow(HWND hWnd);
_user32.SetForegroundWindow.argtypes = [
    wintypes.HWND,
]
_user32.SetForegroundWindow.restype = wintypes.BOOL


def get_last_error() -> int:
    """Return the last Win32 error code for the calling thread."""
    return ctypes.GetLastError()


def register_hotkey(hwnd: Optional[int], hotkey_id: int, modifiers: int, vk: int) -> bool:
    """Register a system-wide hotkey.

    Args:
        hwnd: Handle to the window that will receive WM_HOTKEY messages (or None).
        hotkey_id: Identifier of the hotkey.
        modifiers: Keys that must be pressed in combination (MOD_ALT, MOD_CONTROL, etc.).
        vk: Virtual-key code of the hotkey.

    Returns:
        True if the function succeeds, False otherwise.
    """
    h_wnd = wintypes.HWND(hwnd) if hwnd is not None else None
    result = bool(_user32.RegisterHotKey(h_wnd, hotkey_id, modifiers, vk))
    if not result:
        err = get_last_error()
        logger.warning(
            "RegisterHotKey failed for id=%d (modifiers=0x%04X, vk=0x%02X). Win32 Error=%d",
            hotkey_id,
            modifiers,
            vk,
            err,
        )
    return result


def unregister_hotkey(hwnd: Optional[int], hotkey_id: int) -> bool:
    """Unregister a hotkey previously registered by the calling thread.

    Args:
        hwnd: Handle to the window associated with the hotkey (or None).
        hotkey_id: Identifier of the hotkey to be unregistered.

    Returns:
        True if the function succeeds, False otherwise.
    """
    h_wnd = wintypes.HWND(hwnd) if hwnd is not None else None
    result = bool(_user32.UnregisterHotKey(h_wnd, hotkey_id))
    if not result:
        err = get_last_error()
        logger.debug(
            "UnregisterHotKey failed for id=%d. Win32 Error=%d",
            hotkey_id,
            err,
        )
    return result


def get_foreground_window() -> int:
    """Retrieve a handle to the foreground window."""
    hwnd = _user32.GetForegroundWindow()
    return int(hwnd) if hwnd else 0


def set_foreground_window(hwnd: int) -> bool:
    """Bring the window associated with hwnd into the foreground."""
    if not hwnd:
        return False
    return bool(_user32.SetForegroundWindow(wintypes.HWND(hwnd)))
