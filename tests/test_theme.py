"""Unit tests for ui/theme.py design tokens, typography, and WCAG contrast."""

import pytest
from PySide6.QtGui import QFont

from ui.theme import (
    DARK_THEME,
    LIGHT_THEME,
    MIDNIGHT_THEME,
    ThemeTokens,
    get_app_font,
    get_card_stylesheet,
    get_code_font,
    get_theme,
    is_windows_dark_mode,
)


def _rel_luminance(hex_str: str) -> float:
    """Calculate WCAG relative luminance for a 6-digit hex color."""
    hex_clean = hex_str.lstrip("#")
    r, g, b = [int(hex_clean[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]

    def _adjust(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _adjust(r) + 0.7152 * _adjust(g) + 0.0722 * _adjust(b)


def _contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculate WCAG contrast ratio between two hex colors."""
    l1 = _rel_luminance(hex1)
    l2 = _rel_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def test_midnight_theme_tokens():
    """Verify Midnight tokens match docs/specs/midnight-part1.md specifications exactly."""
    m = MIDNIGHT_THEME
    assert m.background == "#0B0B10"
    assert m.secondary == "#111118"
    assert m.surface == "#171720"
    assert m.elevated == "#1E1E29"
    assert m.border == "#292735"
    assert m.pink == "#FF6BCE"
    assert m.pink_soft == "#F5A4DE"
    assert m.lavender == "#B9A4FF"
    assert m.text == "#F6F3FA"
    assert m.text_secondary == "#A6A1B3"
    assert m.error == "#FF647C"
    assert m.success == "#79E2B5"
    assert m.peach == "#FF9E7D"
    assert m.is_dark is True

    # Midnight replaces old plum dark theme
    assert DARK_THEME == MIDNIGHT_THEME


def test_wcag_text_contrast_ratios_enforcement():
    """Enforce WCAG 4.5:1 minimum contrast ratio for all text colors against all surfaces.

    Rule: Every text colour must pass 4.5:1 on its surface, placeholders included.
    """
    m = MIDNIGHT_THEME
    surfaces = [m.background, m.secondary, m.surface, m.elevated]
    texts = [
        ("text (primary)", m.text),
        ("text_secondary (placeholder/subtitle)", m.text_secondary),
        ("pink (accent)", m.pink),
        ("pink_soft (accent hover)", m.pink_soft),
        ("lavender (highlight)", m.lavender),
        ("error (feedback)", m.error),
        ("success (feedback)", m.success),
    ]

    for surf in surfaces:
        for name, txt in texts:
            ratio = _contrast_ratio(surf, txt)
            assert ratio >= 4.5, (
                f"Contrast failure for {name} ({txt}) on surface ({surf}): "
                f"got {ratio:.2f}:1, expected >= 4.5:1"
            )


def test_get_theme_modes():
    """Verify theme resolution for midnight, light, and system modes."""
    # Explicit midnight
    t_mid = get_theme(theme_mode="midnight")
    assert t_mid.name == "midnight"
    assert t_mid.background == "#0B0B10"

    # Explicit light
    t_light = get_theme(theme_mode="light")
    assert t_light.name == "light"
    assert t_light.background == "#FFF1F6"

    # Legacy force_dark override
    assert get_theme(force_dark=True).name == "midnight"
    assert get_theme(force_dark=False).name == "light"


def test_typography_inter_and_code_fonts():
    """Verify Inter font family resolution and Cascadia Code / Consolas for code."""
    app_font = get_app_font(size=14, bold=True)
    assert app_font.pixelSize() == 14
    families = app_font.families()
    assert any("Inter" in f for f in families) or "Segoe UI Variable Text" in families

    code_font = get_code_font(size=12)
    assert code_font.pixelSize() == 12
    code_families = code_font.families()
    assert "Cascadia Code" in code_families
    assert "Consolas" in code_families


def test_card_stylesheet_generation():
    """Verify stylesheet renders with Midnight tokens."""
    qss = get_card_stylesheet(MIDNIGHT_THEME)
    assert "QFrame#cardContainer" in qss
    assert "#171720" in qss  # Surface
    assert "#FF6BCE" in qss  # Pink accent
    assert "#F6F3FA" in qss  # Text
    assert "presetChip" in qss
