"""Unit tests for ui/theme.py design tokens, typography, font scaling, and WCAG contrast."""

import pytest
from PySide6.QtGui import QFont

from ui.theme import (
    ACCENT_PALETTES_DARK,
    ACCENT_PALETTES_LIGHT,
    DARK_THEME,
    LIGHT_THEME,
    MIDNIGHT_THEME,
    ThemeTokens,
    get_app_font,
    get_card_stylesheet,
    get_code_font,
    get_font_scale,
    get_theme,
    is_windows_dark_mode,
    set_font_scale,
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
    """Verify Midnight tokens match docs/REDESIGN.md Section 3.1 specifications exactly."""
    m = MIDNIGHT_THEME
    assert m.name == "midnight"
    assert m.is_dark is True
    assert m.background == "#0B0B10"
    assert m.secondary == "#111118"
    assert m.surface == "#171720"
    assert m.elevated == "#1E1E29"
    assert m.hover == "#23232F"
    assert m.border == "#292735"
    assert "rgba" in m.hairline
    assert m.text == "#F6F3FA"
    assert m.text_secondary == "#A6A1B3"
    assert m.text_tertiary == "#8F8A9C"
    assert m.accent == "#FF9E7D"  # Default peach
    assert m.accent_2 == "#FF7A90"
    assert m.accent_ink == "#1A0F0C"
    assert "rgba" in m.accent_soft
    assert "rgba" in m.glow
    assert m.success == "#79E2B5"
    assert m.error == "#FF647C"
    assert m.lavender == "#B9A4FF"

    # Backward-compatible property aliases
    assert m.pink == "#FF6BCE"
    assert m.pink_soft == "#F5A4DE"
    assert m.peach == "#FF9E7D"
    assert m.card == m.surface
    assert m.muted == m.text_secondary
    assert m.code_bg == m.secondary
    assert m.pill_bg == m.elevated
    assert m.soft_surface == m.surface
    assert m.accent_hover == m.accent_2
    assert DARK_THEME == MIDNIGHT_THEME


def test_light_theme_tokens():
    """Verify Light tokens match docs/REDESIGN.md Section 3.1 specifications."""
    l = LIGHT_THEME
    assert l.name == "light"
    assert l.is_dark is False
    assert l.background == "#FBF8F6"
    assert l.secondary == "#F4EFEC"
    assert l.surface == "#FFFFFF"
    assert l.elevated == "#FFFFFF"
    assert l.hover == "#EFE8E3"
    assert l.border == "#E9E1DC"
    assert "rgba" in l.hairline
    assert l.text == "#1F1A1D"
    assert l.text_secondary == "#6B6B76"
    assert l.text_tertiary in ("#71717A", "#76767F")
    assert l.accent == "#B4472A"  # Peach for light
    assert l.accent_ink == "#FFFFFF"
    assert l.success == "#057A55"
    assert l.error == "#D32F2F"


def test_accent_palettes_four_accents():
    """Verify all 4 accents (peach, coral, rose, lavender) generate valid dark and light themes."""
    accents = ["peach", "coral", "rose", "lavender"]
    for acc in accents:
        # Midnight
        tm = get_theme(theme_mode="midnight", accent=acc)
        assert tm.name == "midnight"
        assert tm.accent == ACCENT_PALETTES_DARK[acc]["accent"]
        assert tm.accent_ink == ACCENT_PALETTES_DARK[acc]["accent_ink"]

        # Light
        tl = get_theme(theme_mode="light", accent=acc)
        assert tl.name == "light"
        assert tl.accent == ACCENT_PALETTES_LIGHT[acc]["accent"]
        assert tl.accent_ink == ACCENT_PALETTES_LIGHT[acc]["accent_ink"]


def test_wcag_contrast_ratios_midnight():
    """Enforce WCAG 4.5:1 minimum contrast for all text & accent tokens in Midnight theme."""
    for acc in ["peach", "coral", "rose", "lavender"]:
        m = get_theme(theme_mode="midnight", accent=acc)
        surfaces = [m.background, m.secondary, m.surface, m.elevated]
        texts = [
            ("text (primary)", m.text),
            ("text_secondary", m.text_secondary),
            ("text_tertiary", m.text_tertiary),
            ("accent", m.accent),
            ("lavender", m.lavender),
            ("error", m.error),
            ("success", m.success),
        ]
        for surf in surfaces:
            for name, txt in texts:
                ratio = _contrast_ratio(surf, txt)
                assert ratio >= 4.5, (
                    f"Midnight/{acc}: {name} ({txt}) on surface ({surf}) ratio {ratio:.2f}:1 < 4.5:1"
                )

        # accent_ink on filled accent button
        ratio_ink = _contrast_ratio(m.accent, m.accent_ink)
        assert ratio_ink >= 4.5, (
            f"Midnight/{acc}: accent_ink ({m.accent_ink}) on accent ({m.accent}) ratio {ratio_ink:.2f}:1 < 4.5:1"
        )


def test_wcag_contrast_ratios_light():
    """Enforce WCAG 4.5:1 minimum contrast for text & accent tokens in Light theme."""
    for acc in ["peach", "coral", "rose", "lavender"]:
        l = get_theme(theme_mode="light", accent=acc)
        surfaces = [l.background, l.secondary, l.surface, l.elevated]

        # Primary and secondary text on all light surfaces
        for surf in surfaces:
            ratio_pri = _contrast_ratio(surf, l.text)
            assert ratio_pri >= 4.5, f"Light/{acc}: primary text on {surf} ratio {ratio_pri:.2f}:1 < 4.5:1"

            ratio_sec = _contrast_ratio(surf, l.text_secondary)
            assert ratio_sec >= 4.5, f"Light/{acc}: secondary text on {surf} ratio {ratio_sec:.2f}:1 < 4.5:1"

        # text_tertiary on input surfaces (surface & elevated = #FFFFFF)
        ratio_tert = _contrast_ratio(l.surface, l.text_tertiary)
        assert ratio_tert >= 4.5, f"Light/{acc}: tertiary text on surface ratio {ratio_tert:.2f}:1 < 4.5:1"

        # Accent on surface & background
        ratio_acc_surf = _contrast_ratio(l.surface, l.accent)
        assert ratio_acc_surf >= 4.5, f"Light/{acc}: accent on surface ratio {ratio_acc_surf:.2f}:1 < 4.5:1"

        # accent_ink on filled accent button
        ratio_ink = _contrast_ratio(l.accent, l.accent_ink)
        assert ratio_ink >= 4.5, f"Light/{acc}: accent_ink on accent ratio {ratio_ink:.2f}:1 < 4.5:1"

        # Feedback colors
        assert _contrast_ratio(l.surface, l.error) >= 4.5
        assert _contrast_ratio(l.surface, l.success) >= 4.5


def test_get_theme_modes():
    """Verify theme resolution for midnight, light, and system modes."""
    # Explicit midnight
    t_mid = get_theme(theme_mode="midnight")
    assert t_mid.name == "midnight"
    assert t_mid.background == "#0B0B10"

    # Explicit light
    t_light = get_theme(theme_mode="light")
    assert t_light.name == "light"
    assert t_light.background == "#FBF8F6"

    # Legacy force_dark override
    assert get_theme(force_dark=True).name == "midnight"
    assert get_theme(force_dark=False).name == "light"


def test_font_scaling_mechanisms():
    """Verify font scaling multiplier through global setter and parameter overrides."""
    # Reset to default
    set_font_scale(100)
    assert get_font_scale() == 1.0

    f1 = get_app_font(size=14)
    assert f1.pixelSize() == 14

    # Scale 125%
    set_font_scale(125)
    assert get_font_scale() == 1.25
    f2 = get_app_font(size=14)
    assert f2.pixelSize() == int(round(14 * 1.25))  # 18

    # Explicit scale factor override
    f3 = get_app_font(size=14, scale_factor=90)
    assert f3.pixelSize() == int(round(14 * 0.9))  # 13

    # Reset
    set_font_scale(100)
    assert get_font_scale() == 1.0


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
    assert MIDNIGHT_THEME.accent in qss  # Accent
    assert "#F6F3FA" in qss  # Text
    assert "presetChip" in qss
