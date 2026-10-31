"""Main window shell for Peachy desktop assistant.

Implements docs/REDESIGN.md Section 4:
- QMainWindow with native title bar (min 760x520, default 1100x720).
- Geometry persistence to settings.main_window_geometry.
- Close-to-tray handling respecting settings.close_to_tray.
- Native title bar dark mode and backdrop calls (guarded with hasattr for parallel Track B integration).
- Central layout: collapsible Sidebar on the left, QStackedWidget on the right (WelcomeView and ConversationView).
- Full keyboard shortcut support: Ctrl+N, Ctrl+F, Ctrl+B, Esc, Ctrl+Up/Down.
- Compatible with FakeChatSession and real ChatSession via standard signal bindings.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from PySide6.QtCore import QByteArray, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QFont,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import core.win32 as win32
from ui.components.brand_orb import BrandOrb
from ui.components.code_highlighter import render_markdown_html
from ui.components.icons import get_svg_icon
from ui.composer import Composer
from ui.sidebar import Sidebar
from ui.theme import ThemeTokens, get_app_font, get_theme
from ui.welcome_view import WelcomeView

logger = logging.getLogger(__name__)


class ConversationView(QWidget):
    """Active conversation container with header, message stream, and bottom composer."""

    send_requested = Signal(str, list)
    stop_requested = Signal()
    snip_requested = Signal()
    rename_requested = Signal(int)
    delete_requested = Signal(int)

    def __init__(self, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._theme = theme
        self.conv_id: Optional[int] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Header Bar
        self.header_bar = QFrame(self)
        self.header_bar.setFixedHeight(52)
        self.header_bar.setObjectName("chatHeaderBar")

        h_layout = QHBoxLayout(self.header_bar)
        h_layout.setContentsMargins(20, 8, 20, 8)
        h_layout.setSpacing(12)

        self.title_lbl = QLabel("New Chat", self.header_bar)
        self.title_lbl.setFont(get_app_font(15, QFont.Weight.DemiBold))
        h_layout.addWidget(self.title_lbl)

        self.model_chip = QLabel("gemini-2.5-flash", self.header_bar)
        self.model_chip.setObjectName("modelChip")
        self.model_chip.setFont(get_app_font(11, QFont.Weight.Medium))
        h_layout.addWidget(self.model_chip)

        h_layout.addStretch()

        # Action button
        self.more_btn = QPushButton(self.header_bar)
        self.more_btn.setFixedSize(32, 32)
        self.more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.more_btn.setIcon(get_svg_icon("more", color=self._theme.text_secondary, size=16))
        h_layout.addWidget(self.more_btn)

        layout.addWidget(self.header_bar)

        # 2. Messages Scroll Area (max content width 760 px, centred)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.messages_container = QWidget(self.scroll_area)
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(24, 20, 24, 20)
        self.messages_layout.setSpacing(16)
        self.messages_layout.addStretch()

        self.scroll_area.setWidget(self.messages_container)
        layout.addWidget(self.scroll_area, stretch=1)

        # 3. Bottom Composer Wrapper (centred, max 760 px)
        self.composer_container = QWidget(self)
        comp_box = QVBoxLayout(self.composer_container)
        comp_box.setContentsMargins(24, 8, 24, 16)
        comp_box.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.composer = Composer(theme=self._theme, parent=self.composer_container)
        self.composer.setMaximumWidth(760)
        self.composer.send_requested.connect(self.send_requested.emit)
        self.composer.stop_requested.connect(self.stop_requested.emit)
        self.composer.snip_requested.connect(self.snip_requested.emit)
        comp_box.addWidget(self.composer)

        layout.addWidget(self.composer_container)
        self._apply_theme()

    def set_conversation(self, conv_id: int, title: str, messages: List[dict]) -> None:
        """Populate conversation view with loaded history."""
        self.conv_id = conv_id
        self.title_lbl.setText(title or "Chat")
        self.clear_messages()
        for msg in messages:
            self.append_message(msg)

    def clear_messages(self) -> None:
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def append_message(self, msg: dict) -> None:
        """Add user bubble or assistant document block."""
        role = msg.get("role", "user")
        text = msg.get("text", "")
        t = self._theme

        msg_frame = QFrame(self.messages_container)
        msg_frame.setMaximumWidth(760)
        row_layout = QVBoxLayout(msg_frame)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        if role == "user":
            # Right-aligned compact bubble
            bubble = QFrame(msg_frame)
            bubble.setObjectName("userBubble")
            bubble_layout = QVBoxLayout(bubble)
            bubble_layout.setContentsMargins(14, 10, 14, 10)

            lbl = QLabel(text, bubble)
            lbl.setFont(get_app_font(13))
            lbl.setWordWrap(True)
            bubble_layout.addWidget(lbl)

            bubble.setStyleSheet(f"""
                QFrame#userBubble {{
                    background-color: {t.elevated};
                    border: 1px solid {t.border};
                    border-radius: 14px;
                    border-bottom-right-radius: 4px;
                }}
                QLabel {{
                    color: {t.text};
                    background: transparent;
                }}
            """)

            wrapper_h = QHBoxLayout()
            wrapper_h.addStretch()
            wrapper_h.addWidget(bubble)
            row_layout.addLayout(wrapper_h)

        else:
            # Assistant: document style with brand orb and name in accent
            header_h = QHBoxLayout()
            header_h.setSpacing(8)

            orb = BrandOrb(size=18, theme=t, parent=msg_frame)
            header_h.addWidget(orb)

            name_lbl = QLabel("Peachy", msg_frame)
            name_lbl.setFont(get_app_font(13, QFont.Weight.DemiBold))
            name_lbl.setStyleSheet(f"color: {t.accent}; background: transparent;")
            header_h.addWidget(name_lbl)
            header_h.addStretch()
            row_layout.addLayout(header_h)

            browser = QTextBrowser(msg_frame)
            browser.setFrameShape(QFrame.Shape.NoFrame)
            browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            browser.setStyleSheet("background: transparent; border: none;")

            html_body = render_markdown_html(text, theme=t)
            browser.setHtml(html_body)
            # Resize height to fit document
            doc_h = int(browser.document().size().height()) + 20
            browser.setFixedHeight(doc_h)
            row_layout.addWidget(browser)

        # Insert before bottom stretch
        idx = max(0, self.messages_layout.count() - 1)
        self.messages_layout.insertWidget(idx, msg_frame, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Scroll to bottom
        QTimer.singleShot(20, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        vsb = self.scroll_area.verticalScrollBar()
        vsb.setValue(vsb.maximum())

    def apply_theme(self, theme: ThemeTokens) -> None:
        self._theme = theme
        self.composer.apply_theme(theme)
        self.more_btn.setIcon(get_svg_icon("more", color=theme.text_secondary, size=16))
        self._apply_theme()

    def _apply_theme(self) -> None:
        t = self._theme
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {t.background};
            }}
            QFrame#chatHeaderBar {{
                background-color: {t.surface};
                border-bottom: 1px solid {t.border};
            }}
            QLabel {{
                color: {t.text};
                background: transparent;
            }}
            QLabel#modelChip {{
                background-color: {t.secondary};
                border: 1px solid {t.border};
                border-radius: 6px;
                color: {t.text_secondary};
                padding: 3px 8px;
            }}
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {t.hover};
            }}
        """)


class MainWindow(QMainWindow):
    """Main desktop assistant window shell."""

    closed_to_tray = Signal()

    DEFAULT_WIDTH = 1100
    DEFAULT_HEIGHT = 720
    MIN_WIDTH = 760
    MIN_HEIGHT = 520

    def __init__(
        self,
        store: Any = None,
        settings: Any = None,
        chat_session: Any = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.store = store
        self.settings = settings
        self.chat_session = chat_session

        mode = getattr(settings, "theme", "midnight")
        accent = getattr(settings, "accent", "peach")
        self.theme: ThemeTokens = get_theme(theme_mode=mode, accent=accent)

        self.setWindowTitle("Peachy")
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

        self._build_ui()
        self._setup_shortcuts()
        self._wire_chat_session()
        self._apply_window_styling()
        self._restore_geometry()

    def _build_ui(self) -> None:
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Left Sidebar
        self.sidebar = Sidebar(
            store=self.store,
            settings=self.settings,
            theme=self.theme,
            parent=central_widget,
        )
        self.sidebar.new_chat_requested.connect(self.new_chat)
        self.sidebar.conversation_selected.connect(self.load_conversation)
        self.sidebar.conversation_deleted.connect(self._on_conversation_deleted)
        self.sidebar.settings_requested.connect(self.open_settings)
        root_layout.addWidget(self.sidebar)

        # 2. Right Content Area (QStackedWidget)
        self.content_stack = QStackedWidget(central_widget)

        # Index 0: Welcome View
        self.welcome_view = WelcomeView(
            settings=self.settings,
            theme=self.theme,
            parent=self.content_stack,
        )
        self.welcome_view.send_requested.connect(self._on_send_message)
        self.content_stack.addWidget(self.welcome_view)

        # Index 1: Conversation View
        self.conversation_view = ConversationView(
            theme=self.theme,
            parent=self.content_stack,
        )
        self.conversation_view.send_requested.connect(self._on_send_message)
        self.conversation_view.stop_requested.connect(self._on_stop_streaming)
        self.content_stack.addWidget(self.conversation_view)

        root_layout.addWidget(self.content_stack, stretch=1)
        self.content_stack.setCurrentIndex(0)

    def _setup_shortcuts(self) -> None:
        """Register in-app keyboard shortcuts."""
        # Ctrl+N: New chat
        self.sc_new = QShortcut(QKeySequence("Ctrl+N"), self)
        self.sc_new.activated.connect(self.new_chat)

        # Ctrl+F: Focus search field
        self.sc_find = QShortcut(QKeySequence("Ctrl+F"), self)
        self.sc_find.activated.connect(self._focus_search)

        # Ctrl+B: Toggle sidebar
        self.sc_sidebar = QShortcut(QKeySequence("Ctrl+B"), self)
        self.sc_sidebar.activated.connect(self.sidebar.toggle_collapse)

        # Esc: Clear search, stop generation, or close
        self.sc_esc = QShortcut(QKeySequence("Esc"), self)
        self.sc_esc.activated.connect(self._on_escape)

        # Ctrl+Up / Ctrl+Down: Navigate conversations
        self.sc_prev = QShortcut(QKeySequence("Ctrl+Up"), self)
        self.sc_prev.activated.connect(self._navigate_prev_conversation)

        self.sc_next = QShortcut(QKeySequence("Ctrl+Down"), self)
        self.sc_next.activated.connect(self._navigate_next_conversation)

    def _wire_chat_session(self) -> None:
        """Bind ChatSession / FakeChatSession signals."""
        if not self.chat_session:
            return

        cs = self.chat_session
        if hasattr(cs, "conversation_started"):
            cs.conversation_started.connect(self._on_conv_started)
        if hasattr(cs, "conversation_loaded"):
            cs.conversation_loaded.connect(self._on_conv_loaded)
        if hasattr(cs, "title_changed"):
            cs.title_changed.connect(self._on_title_changed)
        if hasattr(cs, "message_added"):
            cs.message_added.connect(self._on_message_added)
        if hasattr(cs, "stream_finished"):
            cs.stream_finished.connect(self._on_stream_finished)
        if hasattr(cs, "status_changed"):
            cs.status_changed.connect(self._on_status_changed)

    def _apply_window_styling(self) -> None:
        t = self.theme
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {t.background};
            }}
        """)

        # Call core.win32 dark title bar and backdrop if present (Track B parallel compatibility)
        hwnd = int(self.winId())
        if hasattr(win32, "set_dark_title_bar"):
            try:
                win32.set_dark_title_bar(hwnd, is_dark=t.is_dark)
            except Exception as exc:
                logger.debug("Could not set dark title bar: %s", exc)

        if hasattr(win32, "set_backdrop"):
            try:
                win32.set_backdrop(hwnd, "mica")
            except Exception as exc:
                logger.debug("Could not set backdrop: %s", exc)

    def apply_theme(
        self,
        theme_mode: Optional[str] = None,
        accent: Optional[str] = None,
        font_scale: Optional[float | int] = None,
    ) -> None:
        """Update main window and all subviews with new theme settings."""
        mode = theme_mode or getattr(self.settings, "theme", "midnight")
        acc = accent or getattr(self.settings, "accent", "peach")
        self.theme = get_theme(theme_mode=mode, accent=acc)

        self.sidebar.apply_theme(self.theme)
        self.welcome_view.apply_theme(self.theme)
        self.conversation_view.apply_theme(self.theme)
        self._apply_window_styling()

    def new_chat(self) -> None:
        """Switch to WelcomeView and reset active chat."""
        if self.chat_session and hasattr(self.chat_session, "new_chat"):
            self.chat_session.new_chat()
        self.content_stack.setCurrentIndex(0)
        self.setWindowTitle("Peachy")
        self.welcome_view.composer.input_edit.setFocus()

    def load_conversation(self, conv_id: int) -> None:
        """Load conversation by ID and show in ConversationView."""
        if self.chat_session and hasattr(self.chat_session, "load"):
            self.chat_session.load(conv_id)
        else:
            # Fallback direct load from store if available
            title = "Chat"
            msgs = []
            if self.store:
                try:
                    c_data = self.store.get_conversation(conv_id)
                    if c_data:
                        title = c_data.get("title") or "Chat"
                    msgs = self.store.get_messages(conv_id)
                except Exception:
                    pass
            self.conversation_view.set_conversation(conv_id, title, msgs)
            self.content_stack.setCurrentIndex(1)
            self.setWindowTitle(f"Peachy - {title}")

    def _on_conv_started(self, conv_id: int, title: str) -> None:
        self.sidebar.refresh_conversations()
        self.sidebar.select_conversation(conv_id)
        self.conversation_view.set_conversation(conv_id, title, [])
        self.content_stack.setCurrentIndex(1)
        self.setWindowTitle(f"Peachy - {title}")

    def _on_conv_loaded(self, conv_id: int, messages: list) -> None:
        title = "Chat"
        if self.store and hasattr(self.store, "get_conversation"):
            c = self.store.get_conversation(conv_id)
            if c:
                title = c.get("title") or "Chat"
        self.conversation_view.set_conversation(conv_id, title, messages)
        self.content_stack.setCurrentIndex(1)
        self.setWindowTitle(f"Peachy - {title}")

    def _on_title_changed(self, conv_id: int, title: str) -> None:
        if self.conversation_view.conv_id == conv_id:
            self.conversation_view.title_lbl.setText(title)
            self.setWindowTitle(f"Peachy - {title}")
        self.sidebar.refresh_conversations()

    def _on_message_added(self, msg: dict) -> None:
        if self.content_stack.currentIndex() == 0:
            self.content_stack.setCurrentIndex(1)
        self.conversation_view.append_message(msg)

    def _on_stream_finished(self, req_id: int, msg: dict) -> None:
        self.conversation_view.append_message(msg)
        self.sidebar.refresh_conversations()

    def _on_status_changed(self, status: str) -> None:
        is_busy = status == "busy"
        self.conversation_view.composer.set_status(is_busy)
        self.welcome_view.composer.set_status(is_busy)

    def _on_send_message(self, text: str, images: list) -> None:
        if self.chat_session and hasattr(self.chat_session, "send"):
            self.chat_session.send(text, images)
        else:
            # Fake/fallback preview
            if self.content_stack.currentIndex() == 0:
                self.content_stack.setCurrentIndex(1)
            user_msg = {"role": "user", "text": text}
            self.conversation_view.append_message(user_msg)

    def _on_stop_streaming(self) -> None:
        if self.chat_session and hasattr(self.chat_session, "stop"):
            self.chat_session.stop()

    def _on_conversation_deleted(self, conv_id: int) -> None:
        if self.conversation_view.conv_id == conv_id:
            self.new_chat()

    def _focus_search(self) -> None:
        if self.sidebar.is_collapsed():
            self.sidebar.set_collapsed(False)
        self.sidebar.search_edit.setFocus()
        self.sidebar.search_edit.selectAll()

    def _on_escape(self) -> None:
        if self.sidebar.search_edit.hasFocus():
            self.sidebar.search_edit.clear()
            self.sidebar.conv_list.setFocus()
            return
        if self.chat_session and hasattr(self.chat_session, "is_streaming") and self.chat_session.is_streaming:
            self._on_stop_streaming()
            return

    def _navigate_prev_conversation(self) -> None:
        cur_row = self.sidebar.conv_list.currentIndex().row()
        if cur_row > 0:
            for r in range(cur_row - 1, -1, -1):
                idx = self.sidebar.model.index(r, 0)
                if not idx.data(Qt.ItemDataRole.UserRole + 1):  # not section
                    self.sidebar.conv_list.setCurrentIndex(idx)
                    cid = idx.data(Qt.ItemDataRole.UserRole + 2)
                    if cid is not None:
                        self.load_conversation(int(cid))
                    break

    def _navigate_next_conversation(self) -> None:
        cur_row = self.sidebar.conv_list.currentIndex().row()
        total_rows = self.sidebar.model.rowCount()
        if cur_row < total_rows - 1:
            for r in range(cur_row + 1, total_rows):
                idx = self.sidebar.model.index(r, 0)
                if not idx.data(Qt.ItemDataRole.UserRole + 1):  # not section
                    self.sidebar.conv_list.setCurrentIndex(idx)
                    cid = idx.data(Qt.ItemDataRole.UserRole + 2)
                    if cid is not None:
                        self.load_conversation(int(cid))
                    break

    def open_settings(self) -> None:
        """Trigger settings dialog / view."""
        logger.info("Settings requested from main window")

    def _restore_geometry(self) -> None:
        geo_str = getattr(self.settings, "main_window_geometry", "")
        if geo_str:
            try:
                b = QByteArray.fromBase64(geo_str.encode("latin1"))
                self.restoreGeometry(b)
            except Exception:
                pass

    def _save_geometry(self) -> None:
        geo_bytes = self.saveGeometry()
        b64_str = geo_bytes.toBase64().data().decode("latin1")
        if hasattr(self.settings, "main_window_geometry"):
            self.settings.main_window_geometry = b64_str
            from config.settings import save_settings
            save_settings(self.settings)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._save_geometry()
        if getattr(self.settings, "close_to_tray", True):
            event.ignore()
            self.hide()
            self.closed_to_tray.emit()
        else:
            event.accept()
