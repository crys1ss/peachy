"""Unit tests for ui/theme.py design tokens and utilities."""

import pytest
from PySide6.QtGui import QFont

from ui.theme import (
    DARK_THEME,
    LIGHT_THEME,
    ThemeTokens,
    get_app_font,
    get_card_stylesheet,
    get_theme,
    is_windows_dark_mode,
)


def test_theme_tokens_contrast_and_palette():
    """Verify light and dark palettes adhere to Peachy design system specifications."""
    # Accent color must match #F472B6 in both modes
    assert LIGHT_THEME.accent == "#F472B6"
    assert DARK_THEME.accent == "#F472B6"

    # Light theme tokens
    assert LIGHT_THEME.card == "#FFFFFF"
    assert LIGHT_THEME.surface == "#FFF1F6"
    assert LIGHT_THEME.text == "#1F1F23"
    assert LIGHT_THEME.muted == "#6B6B76"
    assert LIGHT_THEME.border == "#F9C9DC"
    assert LIGHT_THEME.is_dark is False

    # Dark theme tokens
    assert DARK_THEME.card == "#2A2328"
    assert DARK_THEME.surface == "#1E1A1D"
    assert DARK_THEME.text == "#F5F0F3"
    assert DARK_THEME.border == "#443741"
    assert DARK_THEME.is_dark is True


def test_get_theme_override():
    """Verify force_dark override returns expected theme."""
    light = get_theme(force_dark=False)
    assert light.is_dark is False
    assert light.card == "#FFFFFF"

    dark = get_theme(force_dark=True)
    assert dark.is_dark is True
    assert dark.card == "#2A2328"


def test_font_family_hierarchy():
    """Verify font uses Segoe UI Variable or Segoe UI fallback."""
    font = get_app_font(size=14, weight=QFont.Weight.DemiBold)
    assert font.pixelSize() == 14
    assert font.weight() == QFont.Weight.DemiBold
    families = font.families()
    assert "Segoe UI Variable Text" in families or "Segoe UI" in families


def test_card_stylesheet_generation():
    """Verify stylesheet contains cardContainer and color references."""
    qss_light = get_card_stylesheet(LIGHT_THEME)
    assert "QFrame#cardContainer" in qss_light
    assert "#F472B6" in qss_light
    assert "#FFFFFF" in qss_light

    qss_dark = get_card_stylesheet(DARK_THEME)
    assert "QFrame#cardContainer" in qss_dark
    assert "#2A2328" in qss_dark


def test_theme_no_gradients_and_solid_preset_chips():
    """Verify stylesheets strictly use solid flat colors with zero gradients."""
    for theme in [LIGHT_THEME, DARK_THEME]:
        qss = get_card_stylesheet(theme)
        assert "presetChip" in qss
        assert "gradient" not in qss.lower()
        assert "qlineargradient" not in qss.lower()
