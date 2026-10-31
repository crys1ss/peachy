"""Unit tests for core/win32.py DWM functions: set_dark_title_bar and set_backdrop."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from core.win32 import (
    DWMSBT_AUTO,
    DWMSBT_MAINWINDOW,
    DWMSBT_NONE,
    DWMSBT_TABBEDWINDOW,
    DWMSBT_TRANSIENTWINDOW,
    DWMWA_SYSTEMBACKDROP_TYPE,
    DWMWA_USE_IMMERSIVE_DARK_MODE,
    DWMWA_USE_IMMERSIVE_DARK_MODE_OLD,
    set_backdrop,
    set_dark_title_bar,
)


def test_invalid_hwnd_returns_false():
    """Passing 0 or None for hwnd immediately returns False without DWM invocation."""
    assert set_dark_title_bar(0, True) is False
    assert set_backdrop(0, "mica") is False


def test_dwmapi_none_fallback():
    """When _dwmapi is unavailable, both functions safely return False."""
    with patch("core.win32._dwmapi", None):
        assert set_dark_title_bar(12345, True) is False
        assert set_backdrop(12345, "mica") is False


def test_set_dark_title_bar_modern_success():
    """Modern DWMWA_USE_IMMERSIVE_DARK_MODE (20) succeeds on modern Windows 10/11."""
    mock_dwmapi = MagicMock()
    mock_dwmapi.DwmSetWindowAttribute.return_value = 0  # S_OK

    with patch("core.win32._dwmapi", mock_dwmapi):
        res = set_dark_title_bar(9999, dark=True)
        assert res is True
        mock_dwmapi.DwmSetWindowAttribute.assert_called_once()
        args = mock_dwmapi.DwmSetWindowAttribute.call_args[0]
        assert args[1] == DWMWA_USE_IMMERSIVE_DARK_MODE


def test_set_dark_title_bar_legacy_fallback():
    """If attribute 20 fails, falls back to legacy attribute 19."""
    mock_dwmapi = MagicMock()
    # First call (attr 20) fails with 0x80070057, second call (attr 19) succeeds with 0
    mock_dwmapi.DwmSetWindowAttribute.side_effect = [-2147024809, 0]

    with patch("core.win32._dwmapi", mock_dwmapi):
        res = set_dark_title_bar(9999, dark=True)
        assert res is True
        assert mock_dwmapi.DwmSetWindowAttribute.call_count == 2
        calls = mock_dwmapi.DwmSetWindowAttribute.call_args_list
        assert calls[0][0][1] == DWMWA_USE_IMMERSIVE_DARK_MODE
        assert calls[1][0][1] == DWMWA_USE_IMMERSIVE_DARK_MODE_OLD


def test_set_dark_title_bar_both_fail():
    """If both modern and legacy attributes fail, returns False."""
    mock_dwmapi = MagicMock()
    mock_dwmapi.DwmSetWindowAttribute.side_effect = [-2147024809, -2147024809]

    with patch("core.win32._dwmapi", mock_dwmapi):
        res = set_dark_title_bar(9999, dark=True)
        assert res is False
        assert mock_dwmapi.DwmSetWindowAttribute.call_count == 2


def test_set_backdrop_kinds():
    """Verify set_backdrop maps string names to proper DWMSBT constants."""
    kinds = [
        ("auto", DWMSBT_AUTO),
        ("none", DWMSBT_NONE),
        ("mica", DWMSBT_MAINWINDOW),
        ("acrylic", DWMSBT_TRANSIENTWINDOW),
        ("tabbed", DWMSBT_TABBEDWINDOW),
        ("unknown_default", DWMSBT_MAINWINDOW),
    ]

    for kind_name, expected_val in kinds:
        mock_dwmapi = MagicMock()
        mock_dwmapi.DwmSetWindowAttribute.return_value = 0

        with patch("core.win32._dwmapi", mock_dwmapi):
            res = set_backdrop(8888, kind=kind_name)
            assert res is True
            mock_dwmapi.DwmSetWindowAttribute.assert_called_once()
            args = mock_dwmapi.DwmSetWindowAttribute.call_args[0]
            assert args[1] == DWMWA_SYSTEMBACKDROP_TYPE
