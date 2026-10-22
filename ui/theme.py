"""Design tokens, theme management, and dynamic stylesheet generation for Peachy.

Provides light and dark theme palettes adhering strictly to Peachy's visual identity:
- Accent: #F472B6 (hover #EC4899)
- Light: soft surface #FFF1F6, card #FFFFFF, text #1F1F23, muted #6B6B76, border #F9C9DC
- Dark: surface #1E1A1D, card #2A2328, text #F5F0F3, muted #9E98A0, border #443741
- Font: Segoe UI Variable, fallback Segoe UI
- Automatic Windows light/dark mode synchronization
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import sys
from typing import Optional

from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtCore import Qt

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThemeTokens:
    """Design system color tokens."""

    is_dark: bool
    accent: str           # #F472B6
    accent_hover: str     # #EC4899
    accent_pressed: str   # #DB2777
    surface: str          # #FFF1F6 (light) or #1E1A1D (dark)
    card: str             # #FFFFFF (light) or #2A2328 (dark)
    text: str             # #1F1F23 (light) or #F5F0F3 (dark)
    muted: str            # #6B6B76 (light) or #9E98A0 (dark)
    border: str           # #F9C9DC (light) or #443741 (dark)
    code_bg: str          # #FFF1F6 (light) or #342A32 (dark)
    pill_bg: str          # Soft pink background for badge/chips
    shadow_color: str     # Soft drop shadow

    @property
    def soft_surface(self) -> str:
        """Alias for surface token matching visual identity spec."""
        return self.surface


LIGHT_THEME = ThemeTokens(
    is_dark=False,
    accent="#F472B6",
    accent_hover="#EC4899",
    accent_pressed="#DB2777",
    surface="#FFF1F6",
    card="#FFFFFF",
    text="#1F1F23",
    muted="#6B6B76",
    border="#F9C9DC",
    code_bg="#FFF1F6",
    pill_bg="#FFE4EE",
    shadow_color="rgba(244, 114, 182, 0.18)",
)

DARK_THEME = ThemeTokens(
    is_dark=True,
    accent="#F472B6",
    accent_hover="#EC4899",
    accent_pressed="#DB2777",
    surface="#1E1A1D",
    card="#2A2328",
    text="#F5F0F3",
    muted="#9E98A0",
    border="#443741",
    code_bg="#342A32",
    pill_bg="#3A2C37",
    shadow_color="rgba(0, 0, 0, 0.45)",
)


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


def get_theme(force_dark: Optional[bool] = None) -> ThemeTokens:
    """Return active theme tokens based on OS settings or override."""
    if force_dark is not None:
        return DARK_THEME if force_dark else LIGHT_THEME
    return DARK_THEME if is_windows_dark_mode() else LIGHT_THEME


def get_app_font(
    size: int = 13,
    weight: Optional[QFont.Weight] = None,
    bold: bool = False,
) -> QFont:
    """Create font prioritizing Segoe UI Variable with Segoe UI fallback."""
    font = QFont()
    # Try Segoe UI Variable first, then Segoe UI, then system sans-serif
    font.setFamilies(["Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", "sans-serif"])
    font.setPixelSize(size)
    if weight is not None:
        font.setWeight(weight)
    elif bold:
        font.setWeight(QFont.Weight.Bold)
    else:
        font.setWeight(QFont.Weight.Normal)
    return font


def get_card_stylesheet(theme: ThemeTokens) -> str:
    """Generate stylesheet for main card and components."""
    return f"""
    QFrame#cardContainer {{
        background-color: {theme.card};
        border: 1px solid {theme.border};
        border-radius: 16px;
    }}

    QLabel {{
        color: {theme.text};
        font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif;
    }}

    QLabel#headerTitle {{
        font-size: 15px;
        font-weight: 600;
        color: {theme.text};
    }}

    QLabel#headerSubtitle {{
        font-size: 11px;
        font-weight: 400;
        color: {theme.muted};
    }}

    QLineEdit {{
        background-color: {theme.surface};
        color: {theme.text};
        border: 1.5px solid {theme.border};
        border-radius: 10px;
        padding: 8px 12px;
        font-size: 13px;
        selection-background-color: {theme.accent};
        selection-color: #FFFFFF;
    }}

    QLineEdit:focus {{
        border: 1.5px solid {theme.accent};
        background-color: {theme.card};
    }}

    /* Primary Accent Button (Send) */
    QPushButton#primaryButton {{
        background-color: {theme.accent};
        color: #FFFFFF;
        border: none;
        border-radius: 10px;
        padding: 8px 16px;
        font-size: 13px;
        font-weight: 600;
    }}

    QPushButton#primaryButton:hover {{
        background-color: {theme.accent_hover};
    }}

    QPushButton#primaryButton:pressed {{
        background-color: {theme.accent_pressed};
    }}

    QPushButton#primaryButton:disabled {{
        background-color: {theme.border};
        color: {theme.muted};
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
        background-color: {theme.pill_bg};
        border: 1px solid {theme.accent};
    }}

    QPushButton#secondaryButton:pressed {{
        background-color: {theme.border};
    }}

    /* Header Icon Buttons */
    QPushButton#iconButton {{
        background-color: transparent;
        border: none;
        border-radius: 6px;
        padding: 4px;
        color: {theme.muted};
    }}

    QPushButton#iconButton:hover {{
        background-color: {theme.surface};
        color: {theme.accent};
    }}

    QPushButton#iconButton:checked {{
        background-color: {theme.pill_bg};
        color: {theme.accent};
    }}

    /* Chip Button (Short / Detailed) */
    QPushButton#chipButton {{
        background-color: {theme.surface};
        color: {theme.muted};
        border: 1px solid {theme.border};
        border-radius: 11px;
        padding: 3px 9px;
        font-size: 11px;
        font-weight: 500;
    }}

    QPushButton#chipButton:hover {{
        border-color: {theme.accent};
        color: {theme.accent};
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
        background: {theme.accent};
    }}

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
    """
