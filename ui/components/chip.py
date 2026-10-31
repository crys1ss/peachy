"""Selectable chip component for Peachy.

Features (docs/REDESIGN.md Sections 3.1, 3.3):
- 8 px rounded corners with 4 px padding grid.
- Selectable checkable state with accent_soft background and accent border.
- Vector SVG icon support recoloured dynamically.
- Dynamic theme and accent updates via apply_theme.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QPushButton, QWidget

from ui.components.icons import get_svg_icon
from ui.theme import ThemeTokens, get_app_font, get_theme


class Chip(QPushButton):
    """Interactive selectable chip widget."""

    def __init__(
        self,
        text: str = "",
        icon_name: Optional[str] = None,
        selected: bool = False,
        checkable: bool = True,
        theme: Optional[ThemeTokens] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        self._icon_name = icon_name
        self._theme = theme or get_theme()

        self.setCheckable(checkable)
        self.setChecked(selected)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFont(get_app_font(12, QFont.Weight.Medium))

        self.toggled.connect(self._on_toggled)
        self._update_appearance()

    @property
    def icon_name(self) -> Optional[str]:
        return self._icon_name

    @icon_name.setter
    def icon_name(self, name: Optional[str]) -> None:
        self._icon_name = name
        self._update_appearance()

    def apply_theme(self, theme: ThemeTokens) -> None:
        """Update chip theme tokens and styles."""
        self._theme = theme
        self.setFont(get_app_font(12, QFont.Weight.Medium))
        self._update_appearance()

    def _on_toggled(self, checked: bool) -> None:
        self._update_appearance()

    def _update_appearance(self) -> None:
        t = self._theme
        is_checked = self.isChecked()

        # Update vector icon color according to state
        if self._icon_name:
            icon_color = t.accent if is_checked else t.text_secondary
            self.setIcon(get_svg_icon(self._icon_name, color=icon_color, size=14))
            self.setIconSize(QSize(14, 14))

        if is_checked:
            bg_color = t.accent_soft
            border_color = t.accent
            text_color = t.accent
            hover_bg = t.accent_soft
            hover_border = t.accent_2
        else:
            bg_color = t.secondary
            border_color = t.border
            text_color = t.text_secondary
            hover_bg = t.hover
            hover_border = t.accent

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                border: 1px solid {hover_border};
                color: {text_color if is_checked else t.text};
            }}
            QPushButton:disabled {{
                background-color: {t.secondary};
                border: 1px solid {t.hairline};
                color: {t.text_tertiary};
            }}
        """)
