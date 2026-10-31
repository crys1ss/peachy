"""Welcome view component for Peachy desktop assistant.

Implements docs/REDESIGN.md Section 4 & 6.3:
- Hero BrandOrb (48 px).
- Time-of-day aware greeting ("Good morning / afternoon / evening, <name>").
- Subline: "Ask anything, or snip your screen with Ctrl+Shift+Space".
- 2x2 clickable suggestion cards ("Explain a screenshot", "Debug this error", "Summarise a page", "Draft a reply").
- Centred composer container (max 680 px).
- "Keep your chats?" opt-in card shown when save_history_prompted is False.
- Entrance animation via ui.motion.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ui.components.brand_orb import BrandOrb
from ui.components.icons import get_svg_icon
from ui.composer import Composer
from ui.motion import DUR_WELCOME, fade, slide
from ui.theme import ThemeTokens, get_app_font, get_theme


def get_time_of_day_greeting(now: Optional[datetime] = None, display_name: str = "") -> str:
    """Return friendly greeting based on current hour."""
    if now is None:
        now = datetime.now()
    hour = now.hour

    if 5 <= hour < 12:
        period = "Good morning"
    elif 12 <= hour < 17:
        period = "Good afternoon"
    elif 17 <= hour < 22:
        period = "Good evening"
    else:
        period = "Good night"

    name = display_name.strip()
    if name:
        return f"{period}, {name}"
    return period


class SuggestionCard(QFrame):
    """Clickable suggestion card for prompt starters."""

    clicked = Signal(str)  # prompt

    def __init__(self, title: str, prompt: str, icon_name: str, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.title = title
        self.prompt = prompt
        self.icon_name = icon_name
        self._theme = theme

        self.setObjectName("suggestionCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(64)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self.icon_lbl = QLabel(self)
        self.icon_lbl.setFixedSize(20, 20)
        layout.addWidget(self.icon_lbl)

        self.title_lbl = QLabel(title, self)
        self.title_lbl.setFont(get_app_font(13, QFont.Weight.Medium))
        layout.addWidget(self.title_lbl, stretch=1)

        self._apply_style()

    def _apply_style(self) -> None:
        t = self._theme
        self.setStyleSheet(f"""
            QFrame#suggestionCard {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 12px;
            }}
            QFrame#suggestionCard:hover {{
                background-color: {t.hover};
                border: 1px solid {t.accent};
            }}
            QLabel {{
                color: {t.text};
                background: transparent;
            }}
        """)
        self.icon_lbl.setPixmap(get_svg_icon(self.icon_name, color=t.accent, size=20).pixmap(20, 20))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.prompt)
        super().mousePressEvent(event)


class OptInHistoryCard(QFrame):
    """Dismissible card prompting user to enable history persistence (REDESIGN.md section 6.3)."""

    choice_made = Signal(bool)  # keep_history (True/False)

    def __init__(self, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._theme = theme
        self.setObjectName("optInCard")
        self.setMaximumWidth(680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        shield_icon = QLabel(self)
        shield_icon.setPixmap(get_svg_icon("shield", color=theme.accent, size=18).pixmap(18, 18))
        header_layout.addWidget(shield_icon)

        title_lbl = QLabel("Keep your chats?", self)
        title_lbl.setFont(get_app_font(14, QFont.Weight.DemiBold))
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        desc_lbl = QLabel(
            "Peachy can save conversations on this PC so you can come back to them later. "
            "Your data stays 100% local and private.",
            self,
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setFont(get_app_font(12))
        layout.addWidget(desc_lbl)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.not_now_btn = QPushButton("Not now", self)
        self.not_now_btn.setObjectName("optInNotNow")
        self.not_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.not_now_btn.clicked.connect(lambda: self.choice_made.emit(False))
        btn_layout.addWidget(self.not_now_btn)

        self.keep_btn = QPushButton("Keep chats", self)
        self.keep_btn.setObjectName("optInKeep")
        self.keep_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.keep_btn.clicked.connect(lambda: self.choice_made.emit(True))
        btn_layout.addWidget(self.keep_btn)

        layout.addLayout(btn_layout)
        self._apply_style()

    def _apply_style(self) -> None:
        t = self._theme
        self.setStyleSheet(f"""
            QFrame#optInCard {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 12px;
            }}
            QLabel {{
                color: {t.text};
                background: transparent;
            }}
            QPushButton#optInNotNow {{
                background-color: transparent;
                border: 1px solid {t.border};
                border-radius: 8px;
                color: {t.text_secondary};
                padding: 6px 14px;
                font-size: 12px;
            }}
            QPushButton#optInNotNow:hover {{
                background-color: {t.hover};
            }}
            QPushButton#optInKeep {{
                background-color: {t.accent};
                border: none;
                border-radius: 8px;
                color: {t.accent_ink};
                padding: 6px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton#optInKeep:hover {{
                background-color: {t.accent_2};
            }}
        """)


class WelcomeView(QWidget):
    """Main landing view shown when no conversation is active."""

    prompt_selected = Signal(str)
    send_requested = Signal(str, list)
    snip_requested = Signal()

    def __init__(
        self,
        settings: Any,
        theme: Optional[ThemeTokens] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.settings = settings
        self._theme = theme or get_theme()

        self.setObjectName("welcomeView")
        self._build_ui()
        self._apply_theme()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Centered container scroll area
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget(scroll)
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(24, 30, 24, 30)
        self.content_layout.setSpacing(18)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # 1. Opt-In History Card (conditional)
        self.opt_in_card = OptInHistoryCard(self._theme, content)
        self.opt_in_card.choice_made.connect(self._on_opt_in_choice)
        show_prompt = not getattr(self.settings, "save_history_prompted", False)
        self.opt_in_card.setVisible(show_prompt)
        self.content_layout.addWidget(self.opt_in_card, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Top spacer
        self.content_layout.addSpacing(10)

        # 2. Hero BrandOrb (48 px)
        self.brand_orb = BrandOrb(size=48, theme=self._theme, parent=content)
        self.content_layout.addWidget(self.brand_orb, alignment=Qt.AlignmentFlag.AlignHCenter)

        # 3. Greeting Title
        self.greeting_lbl = QLabel(content)
        self.greeting_lbl.setFont(get_app_font(26, QFont.Weight.DemiBold))
        self.greeting_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.greeting_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        # 4. Subline
        self.subline_lbl = QLabel("Ask anything, or snip your screen with Ctrl+Shift+Space", content)
        self.subline_lbl.setFont(get_app_font(14))
        self.subline_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.subline_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._update_greeting()

        # 5. Centered Composer (680 px max)
        self.composer_wrapper = QWidget(content)
        self.composer_wrapper.setMaximumWidth(680)
        self.composer_wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        comp_wrap_layout = QVBoxLayout(self.composer_wrapper)
        comp_wrap_layout.setContentsMargins(0, 8, 0, 8)

        self.composer = Composer(theme=self._theme, parent=self.composer_wrapper)
        self.composer.send_requested.connect(self.send_requested.emit)
        self.composer.snip_requested.connect(self.snip_requested.emit)
        comp_wrap_layout.addWidget(self.composer)
        self.content_layout.addWidget(self.composer_wrapper, alignment=Qt.AlignmentFlag.AlignHCenter)

        # 6. Suggestion Cards (2x2 grid, 680 px max)
        self.cards_container = QWidget(content)
        self.cards_container.setMaximumWidth(680)
        self.cards_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        cards_grid = QGridLayout(self.cards_container)
        cards_grid.setContentsMargins(0, 8, 0, 0)
        cards_grid.setSpacing(12)

        suggestions = [
            ("Explain a screenshot", "Please explain this screenshot in detail:", "image"),
            ("Debug this error", "Identify the cause of this error and provide a fix:", "scissors"),
            ("Summarise a page", "Summarise the main points and key takeaways from this text:", "sparkle"),
            ("Draft a reply", "Draft a polite and concise response to this message:", "edit"),
        ]

        self.suggestion_cards: list[SuggestionCard] = []
        for idx, (title, prompt, icon_name) in enumerate(suggestions):
            row = idx // 2
            col = idx % 2
            card = SuggestionCard(title, prompt, icon_name, self._theme, self.cards_container)
            card.clicked.connect(self._on_suggestion_clicked)
            cards_grid.addWidget(card, row, col)
            self.suggestion_cards.append(card)

        self.content_layout.addWidget(self.cards_container, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Bottom stretch spacer
        self.content_layout.addStretch()

        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

    def _update_greeting(self) -> None:
        name = getattr(self.settings, "display_name", "")
        self.greeting_lbl.setText(get_time_of_day_greeting(display_name=name))

    def _on_suggestion_clicked(self, prompt: str) -> None:
        # Populate composer or emit prompt
        self.composer.input_edit.setPlainText(prompt)
        self.composer.input_edit.setFocus()
        self.prompt_selected.emit(prompt)

    def _on_opt_in_choice(self, keep_history: bool) -> None:
        if hasattr(self.settings, "save_history"):
            self.settings.save_history = keep_history
        if hasattr(self.settings, "save_history_prompted"):
            self.settings.save_history_prompted = True

        from config.settings import save_settings
        save_settings(self.settings)
        self.opt_in_card.setVisible(False)

    def apply_theme(self, theme: ThemeTokens) -> None:
        """Update welcome view theme dynamically."""
        self._theme = theme
        self.brand_orb.apply_theme(theme)
        self.composer.apply_theme(theme)
        self.opt_in_card._theme = theme
        self.opt_in_card._apply_style()
        for card in self.suggestion_cards:
            card._theme = theme
            card._apply_style()
        self._apply_theme()

    def _apply_theme(self) -> None:
        t = self._theme
        self.setStyleSheet(f"""
            QWidget#welcomeView {{
                background-color: {t.background};
            }}
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QLabel {{
                background: transparent;
            }}
        """)
        self.greeting_lbl.setStyleSheet(f"color: {t.text};")
        self.subline_lbl.setStyleSheet(f"color: {t.text_secondary};")

    def animate_entrance(self) -> None:
        """Run subtle entrance animation."""
        fade(self, start=0.0, end=1.0, ms=DUR_WELCOME, settings=self.settings)
