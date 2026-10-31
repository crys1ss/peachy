"""Design tokens, theme management, and dynamic stylesheet generation for Peachy.

Implements the Midnight Peachy design system as specified in docs/REDESIGN.md Section 3:
- Midnight & Light themes with 4 selectable accents: Peach (#FF9E7D), Coral (#FF8A8A), Rose (#FF7AB6), Lavender (#B9A4FF).
- Exact tokens: background, secondary, surface, elevated, hover, border, hairline, text, text_secondary, text_tertiary, accent, accent_2, accent_ink, accent_soft, glow, success, error, lavender.
- Font scaling via set_font_scale / get_font_scale (90 / 100 / 110 / 125%).
- Backward-compatible property aliases so existing views and tests continue working seamlessly.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import sys
from typing import Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThemeTokens:
    """Design system color tokens conforming strictly to REDESIGN.md section 3.1."""

    name: str
    is_dark: bool
    background: str       # Window canvas, chat area
    secondary: str        # Sidebar, code block background
    surface: str          # Cards, assistant blocks, composer
    elevated: str         # Menus, palette, toasts, user bubble
    hover: str            # Row and button hover
    border: str           # Card and input borders
    hairline: str         # Dividers (rgba string)
    text: str             # Primary text
    text_secondary: str   # Labels, metadata (≥7.1:1 on surface)
    text_tertiary: str    # Placeholders, disabled (≥4.5:1 on surface)
    accent: str           # Primary accent (Peach, Coral, Rose, Lavender)
    accent_2: str         # Secondary accent gradient stop / badges
    accent_ink: str       # Text and icons on accent fills
    accent_soft: str      # Selected chips, active row tint
    glow: str             # Focus glow, orb halo
    success: str          # Online dot, "Copied"
    error: str            # Errors
    lavender: str         # Code types syntax highlight
    pink: str = "#FF6BCE"
    pink_soft: str = "#F5A4DE"
    peach: str = "#FF9E7D"

    @property
    def accent_hover(self) -> str:
        return self.accent_2

    @property
    def accent_pressed(self) -> str:
        return "#F97316" if self.is_dark else "#9A3412"

    @property
    def card(self) -> str:
        return self.surface

    @property
    def muted(self) -> str:
        return self.text_secondary

    @property
    def code_bg(self) -> str:
        return self.secondary

    @property
    def pill_bg(self) -> str:
        return self.elevated

    @property
    def shadow_color(self) -> str:
        return "rgba(0, 0, 0, 0.65)" if self.is_dark else "rgba(0, 0, 0, 0.08)"

    @property
    def soft_surface(self) -> str:
        return self.surface


ACCENT_PALETTES_DARK: Dict[str, Dict[str, str]] = {
    "peach": {
        "accent": "#FF9E7D",
        "accent_2": "#FF7A90",
        "accent_ink": "#1A0F0C",
        "accent_soft": "rgba(255, 158, 125, 0.12)",
        "glow": "rgba(255, 158, 125, 0.22)",
    },
    "coral": {
        "accent": "#FF8A8A",
        "accent_2": "#FF7A90",
        "accent_ink": "#1A0A0A",
        "accent_soft": "rgba(255, 138, 138, 0.12)",
        "glow": "rgba(255, 138, 138, 0.22)",
    },
    "rose": {
        "accent": "#FF7AB6",
        "accent_2": "#FF7A90",
        "accent_ink": "#1A0A14",
        "accent_soft": "rgba(255, 122, 182, 0.12)",
        "glow": "rgba(255, 122, 182, 0.22)",
    },
    "lavender": {
        "accent": "#B9A4FF",
        "accent_2": "#D4A4FF",
        "accent_ink": "#120E24",
        "accent_soft": "rgba(185, 164, 255, 0.12)",
        "glow": "rgba(185, 164, 255, 0.22)",
    },
}

ACCENT_PALETTES_LIGHT: Dict[str, Dict[str, str]] = {
    "peach": {
        "accent": "#B4472A",
        "accent_2": "#D63F5E",
        "accent_ink": "#FFFFFF",
        "accent_soft": "rgba(180, 71, 42, 0.10)",
        "glow": "rgba(180, 71, 42, 0.20)",
    },
    "coral": {
        "accent": "#B83232",
        "accent_2": "#C93B58",
        "accent_ink": "#FFFFFF",
        "accent_soft": "rgba(184, 50, 50, 0.10)",
        "glow": "rgba(184, 50, 50, 0.20)",
    },
    "rose": {
        "accent": "#A82468",
        "accent_2": "#BA2F7C",
        "accent_ink": "#FFFFFF",
        "accent_soft": "rgba(168, 36, 104, 0.10)",
        "glow": "rgba(168, 36, 104, 0.20)",
    },
    "lavender": {
        "accent": "#5A3EB5",
        "accent_2": "#7550C9",
        "accent_ink": "#FFFFFF",
        "accent_soft": "rgba(90, 62, 181, 0.10)",
        "glow": "rgba(90, 62, 181, 0.20)",
    },
}


def is_windows_dark_mode() -> bool:
    """Detect if Windows OS is set to Dark Theme for apps."""
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0
        except Exception as exc:
            logger.debug("Could not read Windows theme registry: %s", exc)

    app = QGuiApplication.instance()
    if app and hasattr(app, "styleHints"):
        hints = app.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() == Qt.ColorScheme.Dark

    return False


def get_theme(
    force_dark: Optional[bool] = None,
    theme_mode: Optional[str] = None,
    accent: Optional[str] = None,
) -> ThemeTokens:
    """Return active theme tokens based on mode, accent, OS settings, or override.

    Args:
        force_dark: Legacy boolean override (True -> Midnight, False -> Light).
        theme_mode: Explicit theme mode ('midnight', 'light', 'system').
        accent: One of 'peach', 'coral', 'rose', 'lavender'.
    """
    acc_key = str(accent).lower().strip() if accent else "peach"
    if acc_key not in ACCENT_PALETTES_DARK:
        acc_key = "peach"

    if theme_mode == "midnight":
        is_dark = True
    elif theme_mode == "light":
        is_dark = False
    elif theme_mode == "system":
        is_dark = is_windows_dark_mode()
    elif force_dark is not None:
        is_dark = force_dark
    else:
        is_dark = is_windows_dark_mode()

    if is_dark:
        pal = ACCENT_PALETTES_DARK[acc_key]
        return ThemeTokens(
            name="midnight",
            is_dark=True,
            background="#0B0B10",
            secondary="#111118",
            surface="#171720",
            elevated="#1E1E29",
            hover="#23232F",
            border="#292735",
            hairline="rgba(255, 255, 255, 0.06)",
            text="#F6F3FA",
            text_secondary="#A6A1B3",
            text_tertiary="#8F8A9C",
            accent=pal["accent"],
            accent_2=pal["accent_2"],
            accent_ink=pal["accent_ink"],
            accent_soft=pal["accent_soft"],
            glow=pal["glow"],
            success="#79E2B5",
            error="#FF647C",
            lavender="#B9A4FF",
        )
    else:
        pal = ACCENT_PALETTES_LIGHT[acc_key]
        return ThemeTokens(
            name="light",
            is_dark=False,
            background="#FBF8F6",
            secondary="#F4EFEC",
            surface="#FFFFFF",
            elevated="#FFFFFF",
            hover="#EFE8E3",
            border="#E9E1DC",
            hairline="rgba(0, 0, 0, 0.06)",
            text="#1F1A1D",
            text_secondary="#6B6B76",
            text_tertiary="#71717A",
            accent=pal["accent"],
            accent_2=pal["accent_2"],
            accent_ink=pal["accent_ink"],
            accent_soft=pal["accent_soft"],
            glow=pal["glow"],
            success="#057A55",
            error="#D32F2F",
            lavender="#7C5CEE",
        )


MIDNIGHT_THEME = get_theme(theme_mode="midnight", accent="peach")
LIGHT_THEME = get_theme(theme_mode="light", accent="peach")
DARK_THEME = MIDNIGHT_THEME

_FONT_INITIALIZED = False
_INTER_FAMILY = "Inter"
_FONT_SCALE: float = 1.0


def set_font_scale(scale: float | int) -> None:
    """Set global font scale factor (e.g. 90, 100, 110, 125 or 0.9, 1.0, 1.1, 1.25)."""
    global _FONT_SCALE
    if scale > 10:
        _FONT_SCALE = float(scale) / 100.0
    else:
        _FONT_SCALE = float(scale)


def get_font_scale() -> float:
    """Get active global font scale factor."""
    return _FONT_SCALE


def init_application_fonts() -> None:
    """Register Inter Variable font from resources/fonts/ if available."""
    global _FONT_INITIALIZED, _INTER_FAMILY
    if _FONT_INITIALIZED:
        return

    if QGuiApplication.instance() is None:
        return

    font_path = Path(__file__).resolve().parent.parent / "resources" / "fonts" / "Inter-Variable.ttf"
    if font_path.exists():
        try:
            font_id = QFontDatabase.addApplicationFont(str(font_path))
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    _INTER_FAMILY = families[0]
                    logger.debug("Registered application font: %s", _INTER_FAMILY)
        except Exception as exc:
            logger.debug("Could not register Inter-Variable.ttf: %s", exc)

    _FONT_INITIALIZED = True


def get_app_font(
    size: int = 13,
    weight: Optional[QFont.Weight] = None,
    bold: bool = False,
    scale_factor: Optional[float | int] = None,
) -> QFont:
    """Create font prioritizing Inter Variable with Segoe UI Variable fallback.

    Applies font scaling multiplier (defaults to global _FONT_SCALE).
    """
    init_application_fonts()
    font = QFont()
    font.setFamilies([_INTER_FAMILY, "Inter", "Segoe UI Variable Text", "Segoe UI", "sans-serif"])

    factor = _FONT_SCALE
    if scale_factor is not None:
        factor = float(scale_factor) / 100.0 if scale_factor > 10 else float(scale_factor)

    scaled_size = max(8, int(round(size * factor)))
    font.setPixelSize(scaled_size)
    if weight is not None:
        font.setWeight(weight)
    elif bold:
        font.setWeight(QFont.Weight.Bold)
    else:
        font.setWeight(QFont.Weight.Normal)
    return font


def get_code_font(size: int = 12, scale_factor: Optional[float | int] = None) -> QFont:
    """Create monospace font prioritizing Cascadia Code with Consolas fallback."""
    font = QFont()
    font.setFamilies(["Cascadia Code", "Consolas", "Courier New", "monospace"])

    factor = _FONT_SCALE
    if scale_factor is not None:
        factor = float(scale_factor) / 100.0 if scale_factor > 10 else float(scale_factor)

    scaled_size = max(8, int(round(size * factor)))
    font.setPixelSize(scaled_size)
    font.setWeight(QFont.Weight.Normal)
    return font


def get_card_stylesheet(theme: ThemeTokens) -> str:
    """Generate stylesheet for main card and components using tokens."""
    return f"""
    QFrame#cardContainer {{
        background-color: {theme.surface};
        border: 1px solid {theme.border};
        border-radius: 16px;
    }}

    QLabel {{
        background-color: transparent;
        color: {theme.text};
        font-family: '{_INTER_FAMILY}', 'Inter', 'Segoe UI Variable Text', 'Segoe UI', sans-serif;
    }}

    QLabel#headerTitle {{
        font-size: 15px;
        font-weight: 600;
        color: {theme.text};
    }}

    QLabel#headerSubtitle {{
        font-size: 11px;
        font-weight: 400;
        color: {theme.text_secondary};
    }}

    QLineEdit {{
        background-color: {theme.secondary};
        color: {theme.text};
        border: 1.5px solid {theme.border};
        border-radius: 10px;
        padding: 8px 12px;
        font-size: 13px;
        selection-background-color: {theme.accent};
        selection-color: {theme.accent_ink};
    }}

    QLineEdit:focus {{
        border: 1.5px solid {theme.accent};
        background-color: {theme.surface};
    }}

    /* Primary Accent Button (Send) */
    QPushButton#primaryButton {{
        background-color: {theme.accent};
        color: {theme.accent_ink};
        border: none;
        border-radius: 10px;
        padding: 8px 16px;
        font-size: 13px;
        font-weight: 600;
    }}

    QPushButton#primaryButton:hover {{
        background-color: {theme.accent_2};
    }}

    QPushButton#primaryButton:pressed {{
        background-color: {theme.accent_pressed};
    }}

    QPushButton#primaryButton:disabled {{
        background-color: {theme.border};
        color: {theme.text_tertiary};
    }}

    /* Secondary Button (Cancel / Retry / New Screenshot) */
    QPushButton#secondaryButton {{
        background-color: {theme.surface};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 10px;
        padding: 7px 14px;
        font-size: 12px;
        font-weight: 500;
    }}

    QPushButton#secondaryButton:hover {{
        background-color: {theme.hover};
        border: 1px solid {theme.accent};
        color: {theme.accent};
    }}

    QPushButton#secondaryButton:pressed {{
        background-color: {theme.secondary};
    }}

    /* Header Icon Buttons */
    QPushButton#iconButton {{
        background-color: transparent;
        border: none;
        border-radius: 6px;
        padding: 4px;
        color: {theme.text_secondary};
    }}

    QPushButton#iconButton:hover {{
        background-color: {theme.hover};
        color: {theme.accent};
    }}

    QPushButton#iconButton:checked {{
        background-color: {theme.hover};
        color: {theme.accent};
    }}

    /* Chip Button (Short / Detailed) */
    QPushButton#chipButton {{
        background-color: {theme.secondary};
        color: {theme.text_secondary};
        border: 1px solid {theme.border};
        border-radius: 11px;
        padding: 3px 9px;
        font-size: 11px;
        font-weight: 500;
    }}

    QPushButton#chipButton:hover {{
        border-color: {theme.accent};
        color: {theme.accent};
        background-color: {theme.hover};
    }}

    /* Action Preset Chips in AskView */
    QPushButton#presetChip {{
        background-color: {theme.secondary};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 8px;
        padding: 5px 8px;
        font-size: 11px;
        font-weight: 500;
    }}

    QPushButton#presetChip:hover {{
        background-color: {theme.hover};
        border-color: {theme.accent};
        color: {theme.accent};
    }}

    /* Error Title */
    QLabel#errorTitle {{
        font-size: 14px;
        font-weight: 600;
        color: {theme.error};
    }}
    """
