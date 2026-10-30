"""Design tokens, theme management, and dynamic stylesheet generation for Peachy.

Provides Midnight, Light, and System themes adhering to Peachy's visual identity:
- Midnight: background #0B0B10, secondary #111118, surface #171720, elevated #1E1E29, border #292735
- Accents: pink #FF6BCE, pink soft #F5A4DE, lavender #B9A4FF, peach highlight #FF9E7D
- Typography: text #F6F3FA, text secondary #A6A1B3, error #FF647C, success #79E2B5
- Font: Inter Variable with Segoe UI Variable fallback; Cascadia Code / Consolas for code
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThemeTokens:
    """Design system color tokens."""

    name: str
    is_dark: bool
    background: str       # #0B0B10
    secondary: str        # #111118
    surface: str          # #171720
    elevated: str         # #1E1E29
    border: str           # #292735
    pink: str             # #FF6BCE
    pink_soft: str        # #F5A4DE
    lavender: str         # #B9A4FF
    text: str             # #F6F3FA
    text_secondary: str   # #A6A1B3
    error: str            # #FF647C
    success: str          # #79E2B5
    peach: str            # #FF9E7D (brand orb highlight only)

    # Backward compatibility properties for existing modules & tests
    @property
    def accent(self) -> str:
        return self.pink

    @property
    def accent_hover(self) -> str:
        return self.pink_soft

    @property
    def accent_pressed(self) -> str:
        return "#E055B3" if self.is_dark else "#DB2777"

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
        return "rgba(0, 0, 0, 0.65)" if self.is_dark else "rgba(244, 114, 182, 0.18)"

    @property
    def soft_surface(self) -> str:
        return self.surface


MIDNIGHT_THEME = ThemeTokens(
    name="midnight",
    is_dark=True,
    background="#0B0B10",
    secondary="#111118",
    surface="#171720",
    elevated="#1E1E29",
    border="#292735",
    pink="#FF6BCE",
    pink_soft="#F5A4DE",
    lavender="#B9A4FF",
    text="#F6F3FA",
    text_secondary="#A6A1B3",
    error="#FF647C",
    success="#79E2B5",
    peach="#FF9E7D",
)

# Midnight replaces the old plum dark theme
DARK_THEME = MIDNIGHT_THEME

LIGHT_THEME = ThemeTokens(
    name="light",
    is_dark=False,
    background="#FFF1F6",
    secondary="#FFE4EE",
    surface="#FFFFFF",
    elevated="#FFF8FA",
    border="#F9C9DC",
    pink="#FF6BCE",
    pink_soft="#F5A4DE",
    lavender="#9065FF",
    text="#1F1F23",
    text_secondary="#6B6B76",
    error="#EF4444",
    success="#10B981",
    peach="#FF9E7D",
)


_FONT_INITIALIZED = False
_INTER_FAMILY = "Inter"


def init_application_fonts() -> None:
    """Register Inter Variable font from resources/fonts/ if available."""
    global _FONT_INITIALIZED, _INTER_FAMILY
    if _FONT_INITIALIZED:
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

    # Fallback to Qt styleHints
    app = QGuiApplication.instance()
    if app and hasattr(app, "styleHints"):
        hints = app.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() == Qt.ColorScheme.Dark

    return False


def get_theme(
    force_dark: Optional[bool] = None,
    theme_mode: Optional[str] = None,
) -> ThemeTokens:
    """Return active theme tokens based on settings, OS settings, or override.

    Args:
        force_dark: Legacy boolean override (True -> Midnight, False -> Light).
        theme_mode: Explicit theme mode ('midnight', 'light', 'system').
    """
    if theme_mode == "midnight":
        return MIDNIGHT_THEME
    if theme_mode == "light":
        return LIGHT_THEME
    if theme_mode == "system":
        return MIDNIGHT_THEME if is_windows_dark_mode() else LIGHT_THEME

    if force_dark is not None:
        return MIDNIGHT_THEME if force_dark else LIGHT_THEME

    return MIDNIGHT_THEME if is_windows_dark_mode() else LIGHT_THEME


def get_app_font(
    size: int = 13,
    weight: Optional[QFont.Weight] = None,
    bold: bool = False,
) -> QFont:
    """Create font prioritizing Inter Variable with Segoe UI Variable fallback."""
    init_application_fonts()
    font = QFont()
    font.setFamilies([_INTER_FAMILY, "Inter", "Segoe UI Variable Text", "Segoe UI", "sans-serif"])
    font.setPixelSize(size)
    if weight is not None:
        font.setWeight(weight)
    elif bold:
        font.setWeight(QFont.Weight.Bold)
    else:
        font.setWeight(QFont.Weight.Normal)
    return font


def get_code_font(size: int = 12) -> QFont:
    """Create monospace font prioritizing Cascadia Code with Consolas fallback."""
    font = QFont()
    font.setFamilies(["Cascadia Code", "Consolas", "Courier New", "monospace"])
    font.setPixelSize(size)
    font.setWeight(QFont.Weight.Normal)
    return font


def get_card_stylesheet(theme: ThemeTokens) -> str:
    """Generate stylesheet for main card and components using Midnight tokens."""
    return f"""
    QFrame#cardContainer {{
        background-color: {theme.surface};
        border: 1px solid {theme.border};
        border-radius: 16px;
    }}

    QLabel {{
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
        selection-background-color: {theme.pink};
        selection-color: {theme.background};
    }}

    QLineEdit:focus {{
        border: 1.5px solid {theme.pink};
        background-color: {theme.surface};
    }}

    /* Primary Accent Button (Send) */
    QPushButton#primaryButton {{
        background-color: {theme.pink};
        color: {theme.background};
        border: none;
        border-radius: 10px;
        padding: 8px 16px;
        font-size: 13px;
        font-weight: 600;
    }}

    QPushButton#primaryButton:hover {{
        background-color: {theme.pink_soft};
    }}

    QPushButton#primaryButton:pressed {{
        background-color: {theme.accent_pressed};
    }}

    QPushButton#primaryButton:disabled {{
        background-color: {theme.border};
        color: {theme.text_secondary};
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
        background-color: {theme.elevated};
        border: 1px solid {theme.pink};
        color: {theme.pink};
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
        background-color: {theme.elevated};
        color: {theme.pink};
    }}

    QPushButton#iconButton:checked {{
        background-color: {theme.elevated};
        color: {theme.pink};
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
        border-color: {theme.pink};
        color: {theme.pink};
    }}

    /* Action Preset Chips in AskView (solid flat colors) */
    QPushButton#presetChip {{
        background-color: {theme.secondary};
        color: {theme.text};
        border: 1px solid {theme.border};
        border-radius: 9px;
        padding: 5px 10px;
        font-size: 11px;
        font-weight: 500;
    }}

    QPushButton#presetChip:hover {{
        background-color: {theme.elevated};
        border-color: {theme.pink};
        color: {theme.pink};
    }}

    QPushButton#presetChip:pressed {{
        background-color: {theme.surface};
    }}

    /* Answer markdown area */
    QTextBrowser#answerBrowser {{
        background-color: transparent;
        color: {theme.text};
        border: none;
        font-size: 13px;
        line-height: 1.5;
    }}

    /* Smooth Scrollbar */
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 6px;
        margin: 4px 0px 4px 0px;
    }}

    QScrollBar::handle:vertical {{
        background: {theme.border};
        min-height: 24px;
        border-radius: 3px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {theme.pink};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
    """
