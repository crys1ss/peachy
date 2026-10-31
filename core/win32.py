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

# int GetWindowTextLengthW(HWND hWnd);
_user32.GetWindowTextLengthW.argtypes = [
    wintypes.HWND,
]
_user32.GetWindowTextLengthW.restype = ctypes.c_int

# int GetWindowTextW(HWND hWnd, LPWSTR lpString, int nMaxCount);
_user32.GetWindowTextW.argtypes = [
    wintypes.HWND,
    wintypes.LPWSTR,
    ctypes.c_int,
]
_user32.GetWindowTextW.restype = ctypes.c_int


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


# Win32 Constants for Low-Level Keyboard Hook
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

# Virtual Key Codes
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12       # Alt key
VK_C = 0x43          # 'C' key
VK_LWIN = 0x5B       # Left Windows key
VK_RWIN = 0x5C       # Right Windows key

# KBDLLHOOKSTRUCT flags
LLKHF_EXTENDED = 0x00000001
LLKHF_INJECTED = 0x00000010
LLKHF_ALTDOWN = 0x00000020
LLKHF_UP = 0x00000080


class KBDLLHOOKSTRUCT(ctypes.Structure):
    """Win32 KBDLLHOOKSTRUCT containing low-level keyboard input event information."""

    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


# Hook callback function prototype: LRESULT (int, WPARAM, LPARAM)
HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

# Configure Low-Level Hook ctypes signatures
# HHOOK SetWindowsHookExW(int idHook, HOOKPROC lpfn, HINSTANCE hmod, DWORD dwThreadId);
_user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    wintypes.HINSTANCE,
    wintypes.DWORD,
]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK

# BOOL UnhookWindowsHookEx(HHOOK hhk);
_user32.UnhookWindowsHookEx.argtypes = [
    wintypes.HHOOK,
]
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL

# LRESULT CallNextHookEx(HHOOK hhk, int nCode, WPARAM wParam, LPARAM lParam);
_user32.CallNextHookEx.argtypes = [
    wintypes.HHOOK,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
_user32.CallNextHookEx.restype = ctypes.c_longlong

# SHORT GetKeyState(int nVirtKey);
_user32.GetKeyState.argtypes = [
    ctypes.c_int,
]
_user32.GetKeyState.restype = ctypes.c_short

# HMODULE GetModuleHandleW(LPCWSTR lpModuleName);
_kernel32.GetModuleHandleW.argtypes = [
    wintypes.LPCWSTR,
]
_kernel32.GetModuleHandleW.restype = wintypes.HMODULE


def get_foreground_window() -> int:
    """Retrieve a handle to the foreground window."""
    hwnd = _user32.GetForegroundWindow()
    return int(hwnd) if hwnd else 0


def set_foreground_window(hwnd: int) -> bool:
    """Bring the window associated with hwnd into the foreground."""
    if not hwnd:
        return False
    return bool(_user32.SetForegroundWindow(wintypes.HWND(hwnd)))


def get_window_text(hwnd: int) -> str:
    """Retrieve the text of the specified window's title bar (if it has one)."""
    if not hwnd:
        return ""
    length = _user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    copied = _user32.GetWindowTextW(wintypes.HWND(hwnd), buffer, length + 1)
    if copied <= 0:
        return ""
    return buffer.value


def set_windows_hook(id_hook: int, proc: Any, hmod: int = 0, thread_id: int = 0) -> Optional[int]:
    """Install an application-defined hook procedure into a hook chain."""
    h_mod = wintypes.HINSTANCE(hmod) if hmod else _kernel32.GetModuleHandleW(None)
    hhk = _user32.SetWindowsHookExW(id_hook, proc, h_mod, thread_id)
    if not hhk:
        err = get_last_error()
        logger.warning("SetWindowsHookExW failed for idHook=%d. Win32 Error=%d", id_hook, err)
        return None
    return int(hhk)


def unhook_windows_hook(hhk: int) -> bool:
    """Remove a hook procedure installed in a hook chain by SetWindowsHookEx."""
    if not hhk:
        return False
    result = bool(_user32.UnhookWindowsHookEx(wintypes.HHOOK(hhk)))
    if not result:
        err = get_last_error()
        logger.warning("UnhookWindowsHookEx failed for hhk=%d. Win32 Error=%d", hhk, err)
    return result


def call_next_hook(hhk: Optional[int], n_code: int, w_param: int, l_param: int) -> int:
    """Pass hook information to the next hook procedure in the current hook chain."""
    h_hook = wintypes.HHOOK(hhk) if hhk else None
    return int(_user32.CallNextHookEx(h_hook, n_code, w_param, l_param))


def get_key_state(vk: int) -> int:
    """Retrieve the status of the specified virtual key."""
    return int(_user32.GetKeyState(vk))


def is_key_down(vk: int) -> bool:
    """Return True if the high-order bit indicates the key is down."""
    return bool((get_key_state(vk) & 0x8000) != 0)


# SystemParametersInfo action constants
SPI_GETCLIENTAREAANIMATION = 0x1042

_user32.SystemParametersInfoW.argtypes = [
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    wintypes.UINT,
]
_user32.SystemParametersInfoW.restype = wintypes.BOOL


def get_client_area_animation_enabled() -> bool:
    """Read Windows 'Animation effects' setting (SystemParametersInfo with SPI_GETCLIENTAREAANIMATION).

    Returns:
        True if client area animations are enabled in Windows, False if user disabled animation effects.
    """
    anim_enabled = wintypes.BOOL()
    result = bool(
        _user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION,
            0,
            ctypes.byref(anim_enabled),
            0,
        )
    )
    if not result:
        err = get_last_error()
        logger.debug("SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION) failed. Win32 Error=%d", err)
        return True
    return bool(anim_enabled.value)


# DWM (Desktop Window Manager) configuration
try:
    _dwmapi = ctypes.windll.dwmapi
    _dwmapi.DwmSetWindowAttribute.argtypes = [
        wintypes.HWND,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
except (AttributeError, OSError):
    _dwmapi = None

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_USE_IMMERSIVE_DARK_MODE_OLD = 19
DWMWA_SYSTEMBACKDROP_TYPE = 38

DWMSBT_AUTO = 0
DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2        # Mica
DWMSBT_TRANSIENTWINDOW = 3   # Acrylic
DWMSBT_TABBEDWINDOW = 4      # Tabbed / Mica Alt


def set_dark_title_bar(hwnd: int, dark: bool) -> bool:
    """Set the window's native title bar to dark or light mode using DwmSetWindowAttribute.

    Uses DWMWA_USE_IMMERSIVE_DARK_MODE=20 (Windows 10 20H1+ / Windows 11; falls back to 19 on 1903/1909).
    A safe no-op returning False on older Windows or unsupported platforms.
    """
    if not hwnd or _dwmapi is None:
        return False

    val = wintypes.BOOL(1 if dark else 0)
    # Modern attribute 20
    hr = _dwmapi.DwmSetWindowAttribute(
        wintypes.HWND(hwnd),
        DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(val),
        ctypes.sizeof(val),
    )
    if hr == 0:
        return True

    # Legacy attribute 19
    hr_old = _dwmapi.DwmSetWindowAttribute(
        wintypes.HWND(hwnd),
        DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
        ctypes.byref(val),
        ctypes.sizeof(val),
    )
    return hr_old == 0


def set_backdrop(hwnd: int, kind: str | int = "mica") -> bool:
    """Set the window backdrop type using DwmSetWindowAttribute (DWMWA_SYSTEMBACKDROP_TYPE = 38).

    Supported kinds on Windows 11 22H2+ (Build 22621+):
    - "auto" (0)
    - "none" (1)
    - "mica" (2)
    - "acrylic" (3)
    - "tabbed" (4)
    A silent no-op returning False on older Windows or unsupported platforms.
    """
    if not hwnd or _dwmapi is None:
        return False

    kind_map = {
        "auto": DWMSBT_AUTO,
        "none": DWMSBT_NONE,
        "mica": DWMSBT_MAINWINDOW,
        "acrylic": DWMSBT_TRANSIENTWINDOW,
        "tabbed": DWMSBT_TABBEDWINDOW,
    }
    if isinstance(kind, str):
        val_int = kind_map.get(kind.lower(), DWMSBT_MAINWINDOW)
    else:
        val_int = int(kind)

    val = wintypes.DWORD(val_int)
    hr = _dwmapi.DwmSetWindowAttribute(
        wintypes.HWND(hwnd),
        DWMWA_SYSTEMBACKDROP_TYPE,
        ctypes.byref(val),
        ctypes.sizeof(val),
    )
    return hr == 0


