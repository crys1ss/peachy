"""Sidebar navigation component for Peachy desktop assistant.

Implements docs/REDESIGN.md Section 4:
- 264 px expanded / 64 px collapsed width with smooth animated transition (ui.motion).
- BrandHeader: BrandOrb (22 px), 'peachy' wordmark, collapse/expand toggle button.
- NewChatButton: prominent button with plus icon and Ctrl+N hint.
- SearchField: 150 ms debounce search with clear on Esc (Ctrl+F).
- ConversationList: QListView with custom ConversationDelegate:
  - Pinned and chronological sections (Today, Yesterday, Previous 7 days, etc.) using history.grouping.
  - Title (1 line elided), preview (1 line text_tertiary), relative timestamp.
  - Active conversation row has 2 px vertical accent gradient marker on left edge.
  - Hover reveals action menu (Rename, Pin/Unpin, Export, Delete with confirm).
- SidebarFooter: display name profile chip + Settings gear button.
- Remembers collapsed state via settings.sidebar_collapsed.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, List, Optional

from PySide6.QtCore import (
    QEvent,
    QModelIndex,
    QPoint,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPen,
    QStandardItem,
    QStandardItemModel,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from history.grouping import group_conversations
from ui.components.brand_orb import BrandOrb
from ui.components.icons import get_svg_icon
from ui.motion import DUR_SIDEBAR, slide
from ui.theme import ThemeTokens, get_app_font, get_theme

# Item model custom roles
ROLE_IS_SECTION = Qt.ItemDataRole.UserRole + 1
ROLE_CONV_ID = Qt.ItemDataRole.UserRole + 2
ROLE_TITLE = Qt.ItemDataRole.UserRole + 3
ROLE_PREVIEW = Qt.ItemDataRole.UserRole + 4
ROLE_TIME = Qt.ItemDataRole.UserRole + 5
ROLE_PINNED = Qt.ItemDataRole.UserRole + 6


def format_relative_time(dt_val: Any) -> str:
    """Format timestamp into human-readable relative string."""
    if not dt_val:
        return ""
    if isinstance(dt_val, str):
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(dt_val.strip(), fmt)
                break
            except ValueError:
                continue
        else:
            try:
                dt = datetime.fromisoformat(dt_val.strip())
            except Exception:
                return dt_val[:10]
    elif isinstance(dt_val, datetime):
        dt = dt_val
    else:
        return ""

    now = datetime.now()
    diff = now - dt
    secs = int(diff.total_seconds())

    if secs < 60:
        return "Just now"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m"
    hours = mins // 60
    if hours < 24 and dt.date() == now.date():
        return f"{hours}h"
    if (now.date() - dt.date()).days == 1:
        return "Yesterday"
    if diff.days < 7:
        return f"{diff.days}d"
    return dt.strftime("%b %d")


class ConversationDelegate(QStyledItemDelegate):
    """Custom painted delegate for sidebar conversation rows and section headers."""

    menu_requested = Signal(int, QPoint)  # conv_id, global_pos

    def __init__(self, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._theme = theme
        self.hovered_index: Optional[QModelIndex] = None

    def apply_theme(self, theme: ThemeTokens) -> None:
        self._theme = theme

    def sizeHint(self, option, index: QModelIndex) -> QSize:  # noqa: N802
        if index.data(ROLE_IS_SECTION):
            return QSize(option.rect.width(), 28)
        return QSize(option.rect.width(), 52)

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:  # noqa: N802
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = option.rect
        t = self._theme

        if index.data(ROLE_IS_SECTION):
            # Section header label
            title = str(index.data(ROLE_TITLE) or "").upper()
            painter.setFont(get_app_font(10, QFont.Weight.DemiBold))
            painter.setPen(QColor(t.text_tertiary))
            header_rect = rect.adjusted(12, 6, -12, 0)
            painter.drawText(header_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
            painter.restore()
            return

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = False
        if option.widget is not None:
            try:
                is_hovered = option.rect.contains(option.widget.mapFromGlobal(QCursor.pos()))
            except Exception:
                is_hovered = False

        bg_rect = rect.adjusted(6, 2, -6, -2)

        # 1. Background fill
        if is_selected:
            painter.setBrush(QColor(t.accent_soft))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bg_rect, 8, 8)

            # 2 px vertical accent gradient marker at left edge
            marker_rect = QRectF(bg_rect.left() + 2, bg_rect.top() + 8, 2.5, bg_rect.height() - 16)
            marker_grad = QLinearGradient(marker_rect.topLeft(), marker_rect.bottomLeft())
            marker_grad.setColorAt(0.0, QColor(t.accent))
            marker_grad.setColorAt(1.0, QColor(t.accent_2))
            painter.setBrush(marker_grad)
            painter.drawRoundedRect(marker_rect, 1.25, 1.25)
        elif is_hovered:
            painter.setBrush(QColor(t.hover))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bg_rect, 8, 8)

        # 2. Texts
        title = str(index.data(ROLE_TITLE) or "Untitled")
        preview = str(index.data(ROLE_PREVIEW) or "")
        rel_time = str(index.data(ROLE_TIME) or "")
        is_pinned = bool(index.data(ROLE_PINNED))

        text_left = bg_rect.left() + 12
        text_right = bg_rect.right() - (36 if is_hovered else 8)
        content_width = max(10, text_right - text_left)

        # Title line
        painter.setFont(get_app_font(13, QFont.Weight.Medium if is_selected else QFont.Weight.Normal))
        painter.setPen(QColor(t.text if not is_selected else t.accent))

        fm_title = QFontMetrics(painter.font())
        elided_title = fm_title.elidedText(title, Qt.TextElideMode.ElideRight, content_width - (45 if rel_time else 0))

        title_y = bg_rect.top() + 18
        painter.drawText(text_left, title_y, elided_title)

        # Timestamp (top right)
        if rel_time and not is_hovered:
            painter.setFont(get_app_font(11))
            painter.setPen(QColor(t.text_tertiary))
            painter.drawText(
                QRect(bg_rect.right() - 50, bg_rect.top() + 6, 44, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                rel_time,
            )

        # Preview line (second line)
        painter.setFont(get_app_font(11))
        painter.setPen(QColor(t.text_tertiary))
        fm_prev = QFontMetrics(painter.font())
        elided_prev = fm_prev.elidedText(preview, Qt.TextElideMode.ElideRight, content_width)
        preview_y = bg_rect.top() + 36
        painter.drawText(text_left, preview_y, elided_prev)

        # Hover action dots icon
        if is_hovered:
            dots_icon = get_svg_icon("more", color=t.text_secondary, size=16)
            dots_rect = QRect(bg_rect.right() - 26, bg_rect.top() + int((bg_rect.height() - 20) / 2), 20, 20)
            dots_icon.paint(painter, dots_rect)

        # Pin badge
        if is_pinned and not is_hovered:
            pin_icon = get_svg_icon("pin", color=t.accent, size=12)
            pin_rect = QRect(bg_rect.right() - 20, bg_rect.top() + 6, 12, 12)
            pin_icon.paint(painter, pin_rect)

        painter.restore()


class Sidebar(QFrame):
    """Main navigation sidebar container."""

    new_chat_requested = Signal()
    conversation_selected = Signal(int)   # conv_id
    conversation_renamed = Signal(int, str)
    conversation_pinned_toggled = Signal(int, bool)
    conversation_deleted = Signal(int)
    conversation_exported = Signal(int)
    settings_requested = Signal()
    collapsed_changed = Signal(bool)

    EXPANDED_WIDTH = 264
    COLLAPSED_WIDTH = 64

    def __init__(
        self,
        store: Any,
        settings: Any,
        theme: Optional[ThemeTokens] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.store = store
        self.settings = settings
        self._theme = theme or get_theme()
        self._is_collapsed: bool = bool(getattr(settings, "sidebar_collapsed", False))

        self.setObjectName("sidebarFrame")
        self.setFixedWidth(self.COLLAPSED_WIDTH if self._is_collapsed else self.EXPANDED_WIDTH)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(self._on_search_debounced)

        self._build_ui()
        self._apply_theme()
        self.refresh_conversations()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 12, 10, 12)
        main_layout.setSpacing(10)

        # 1. Header (Brand orb, title, collapse toggle)
        self.header_layout = QHBoxLayout()
        self.header_layout.setContentsMargins(2, 0, 2, 0)
        self.header_layout.setSpacing(8)

        self.brand_orb = BrandOrb(size=22, theme=self._theme, parent=self)
        self.header_layout.addWidget(self.brand_orb)

        self.brand_title = QLabel("peachy", self)
        self.brand_title.setFont(get_app_font(15, QFont.Weight.DemiBold))
        self.header_layout.addWidget(self.brand_title)
        self.header_layout.addStretch()

        self.collapse_btn = QPushButton(self)
        self.collapse_btn.setFixedSize(28, 28)
        self.collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_btn.setToolTip("Toggle sidebar (Ctrl+B)")
        self.collapse_btn.clicked.connect(self.toggle_collapse)
        self.header_layout.addWidget(self.collapse_btn)
        main_layout.addLayout(self.header_layout)

        # 2. New Chat Button
        self.new_chat_btn = QPushButton("New chat", self)
        self.new_chat_btn.setObjectName("newChatBtn")
        self.new_chat_btn.setFixedHeight(36)
        self.new_chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_chat_btn.setToolTip("Start a new chat (Ctrl+N)")
        self.new_chat_btn.clicked.connect(self.new_chat_requested.emit)
        main_layout.addWidget(self.new_chat_btn)

        # 3. Search Field
        self.search_edit = QLineEdit(self)
        self.search_edit.setObjectName("sidebarSearch")
        self.search_edit.setFixedHeight(34)
        self.search_edit.setPlaceholderText("Search chats… (Ctrl+F)")
        self.search_edit.textChanged.connect(lambda: self._search_timer.start())
        main_layout.addWidget(self.search_edit)

        # 4. Conversation List (QListView)
        self.model = QStandardItemModel(self)
        self.conv_list = QListView(self)
        self.conv_list.setObjectName("conversationListView")
        self.conv_list.setModel(self.model)
        self.delegate = ConversationDelegate(self._theme, self.conv_list)
        self.conv_list.setItemDelegate(self.delegate)
        self.conv_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.conv_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.conv_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.conv_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.conv_list.setMouseTracking(True)
        self.conv_list.clicked.connect(self._on_item_clicked)
        self.conv_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.conv_list.customContextMenuRequested.connect(self._show_context_menu)
        main_layout.addWidget(self.conv_list, stretch=1)

        # 5. Footer (Profile Chip + Settings Gear)
        self.footer_layout = QHBoxLayout()
        self.footer_layout.setContentsMargins(2, 4, 2, 0)
        self.footer_layout.setSpacing(6)

        self.profile_btn = QPushButton(self)
        self.profile_btn.setObjectName("profileChip")
        self.profile_btn.setFixedHeight(34)
        self.profile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.profile_btn.clicked.connect(self.settings_requested.emit)
        self._update_profile_chip()
        self.footer_layout.addWidget(self.profile_btn, stretch=1)

        self.settings_btn = QPushButton(self)
        self.settings_btn.setObjectName("settingsBtn")
        self.settings_btn.setFixedSize(34, 34)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setToolTip("Settings (Ctrl+,)")
        self.settings_btn.clicked.connect(self.settings_requested.emit)
        self.footer_layout.addWidget(self.settings_btn)

        main_layout.addLayout(self.footer_layout)

        # Update initial collapsed visual state
        self._update_collapsed_layout()

    def _update_profile_chip(self) -> None:
        display_name = getattr(self.settings, "display_name", "").strip() or "User"
        self.profile_btn.setText(display_name)
        self.profile_btn.setIcon(get_svg_icon("info", color=self._theme.success, size=14))

    def apply_theme(self, theme: ThemeTokens) -> None:
        """Update sidebar theme tokens dynamically."""
        self._theme = theme
        self.brand_orb.apply_theme(theme)
        self.delegate.apply_theme(theme)
        self._update_profile_chip()
        self._apply_theme()
        self.conv_list.viewport().update()

    def _apply_theme(self) -> None:
        t = self._theme
        self.setStyleSheet(f"""
            QFrame#sidebarFrame {{
                background-color: {t.secondary};
                border-right: 1px solid {t.border};
            }}
            QLabel {{
                color: {t.text};
                background: transparent;
            }}
            QPushButton {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
                color: {t.text};
                padding: 6px;
            }}
            QPushButton:hover {{
                background-color: {t.hover};
            }}
            QPushButton#newChatBtn {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 10px;
                color: {t.text};
                font-weight: 600;
                padding: 6px 12px;
                text-align: left;
            }}
            QPushButton#newChatBtn:hover {{
                background-color: {t.hover};
                border: 1px solid {t.accent};
            }}
            QLineEdit#sidebarSearch {{
                background-color: {t.surface};
                color: {t.text};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 12px;
            }}
            QLineEdit#sidebarSearch:focus {{
                border: 1px solid {t.accent};
            }}
            QListView#conversationListView {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
            QPushButton#profileChip {{
                background-color: transparent;
                text-align: left;
                padding-left: 8px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton#profileChip:hover {{
                background-color: {t.hover};
            }}
        """)

        self.collapse_btn.setIcon(get_svg_icon("sidebar", color=t.text_secondary, size=16))
        self.new_chat_btn.setIcon(get_svg_icon("plus", color=t.accent, size=16))
        self.settings_btn.setIcon(get_svg_icon("settings", color=t.text_secondary, size=16))

    def is_collapsed(self) -> bool:
        return self._is_collapsed

    def toggle_collapse(self) -> None:
        self.set_collapsed(not self._is_collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if self._is_collapsed == collapsed:
            return

        self._is_collapsed = collapsed
        if hasattr(self.settings, "sidebar_collapsed"):
            self.settings.sidebar_collapsed = collapsed

        target_w = self.COLLAPSED_WIDTH if collapsed else self.EXPANDED_WIDTH

        from ui.motion import should_animate
        if not should_animate(self.settings):
            self.setFixedWidth(target_w)
            self._update_collapsed_layout()
            self.collapsed_changed.emit(self._is_collapsed)
            return

        def on_done():
            self._update_collapsed_layout()
            self.collapsed_changed.emit(self._is_collapsed)

        slide(self, "maximumWidth", self.width(), target_w, ms=DUR_SIDEBAR, on_finished=on_done, settings=self.settings)
        slide(self, "minimumWidth", self.width(), target_w, ms=DUR_SIDEBAR, settings=self.settings)

    def _update_collapsed_layout(self) -> None:
        c = self._is_collapsed
        self.brand_title.setVisible(not c)
        self.search_edit.setVisible(not c)
        self.profile_btn.setVisible(not c)

        if c:
            self.new_chat_btn.setText("")
            self.new_chat_btn.setFixedSize(36, 36)
            self.new_chat_btn.setStyleSheet(f"""
                QPushButton#newChatBtn {{
                    background-color: {self._theme.surface};
                    border: 1px solid {self._theme.border};
                    border-radius: 18px;
                }}
            """)
        else:
            self.new_chat_btn.setText("New chat")
            self.new_chat_btn.setFixedHeight(36)
            self.new_chat_btn.setMaximumWidth(16777215)
            self.new_chat_btn.setMinimumWidth(0)
            self._apply_theme()

    def refresh_conversations(self) -> None:
        """Fetch conversations from store, apply search filter, and rebuild model groups."""
        if not self.store:
            return

        query = self.search_edit.text().strip().lower()
        try:
            all_convs = self.store.list_conversations()
        except Exception:
            all_convs = []

        if query:
            filtered = [
                c for c in all_convs
                if query in str(c.get("title", "")).lower() or query in str(c.get("preview", "")).lower()
            ]
        else:
            filtered = all_convs

        groups = group_conversations(filtered)

        self.model.clear()
        for section_title, items in groups:
            # Section header item
            header_item = QStandardItem()
            header_item.setData(True, ROLE_IS_SECTION)
            header_item.setData(section_title, ROLE_TITLE)
            header_item.setSelectable(False)
            self.model.appendRow(header_item)

            for conv in items:
                item = QStandardItem()
                item.setData(False, ROLE_IS_SECTION)
                item.setData(conv.get("id"), ROLE_CONV_ID)
                item.setData(conv.get("title") or "New Chat", ROLE_TITLE)
                item.setData(conv.get("preview") or "", ROLE_PREVIEW)
                item.setData(format_relative_time(conv.get("updated_at") or conv.get("created_at")), ROLE_TIME)
                item.setData(bool(conv.get("pinned", False)), ROLE_PINNED)
                self.model.appendRow(item)

    def _on_search_debounced(self) -> None:
        self.refresh_conversations()

    def _on_item_clicked(self, index: QModelIndex) -> None:
        if index.data(ROLE_IS_SECTION):
            return
        cid = index.data(ROLE_CONV_ID)
        if cid is not None:
            self.conversation_selected.emit(int(cid))

    def _show_context_menu(self, pos: QPoint) -> None:
        index = self.conv_list.indexAt(pos)
        if not index.isValid() or index.data(ROLE_IS_SECTION):
            return

        cid = index.data(ROLE_CONV_ID)
        if cid is None:
            return
        cid = int(cid)

        is_pinned = bool(index.data(ROLE_PINNED))
        cur_title = str(index.data(ROLE_TITLE) or "")

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {self._theme.elevated};
                border: 1px solid {self._theme.border};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                color: {self._theme.text};
                padding: 6px 14px;
                font-size: 12px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {self._theme.hover};
                color: {self._theme.accent};
            }}
        """)

        act_rename = menu.addAction(get_svg_icon("edit", color=self._theme.text_secondary, size=14), "Rename")
        act_pin = menu.addAction(
            get_svg_icon("pin", color=self._theme.accent if is_pinned else self._theme.text_secondary, size=14),
            "Unpin" if is_pinned else "Pin",
        )
        act_export = menu.addAction(get_svg_icon("more", color=self._theme.text_secondary, size=14), "Export…")
        menu.addSeparator()
        act_delete = menu.addAction(get_svg_icon("x", color=self._theme.error, size=14), "Delete")

        global_pos = self.conv_list.viewport().mapToGlobal(pos)
        action = menu.exec(global_pos)

        if action == act_rename:
            new_title, ok = QInputDialog.getText(
                self,
                "Rename Chat",
                "Enter conversation title:",
                QLineEdit.EchoMode.Normal,
                cur_title,
            )
            if ok and new_title.strip():
                if hasattr(self.store, "rename_conversation"):
                    self.store.rename_conversation(cid, new_title.strip())
                self.conversation_renamed.emit(cid, new_title.strip())
                self.refresh_conversations()

        elif action == act_pin:
            new_pin = not is_pinned
            if hasattr(self.store, "set_pinned"):
                self.store.set_pinned(cid, new_pin)
            self.conversation_pinned_toggled.emit(cid, new_pin)
            self.refresh_conversations()

        elif action == act_export:
            self.conversation_exported.emit(cid)

        elif action == act_delete:
            confirm = QMessageBox.question(
                self,
                "Delete Chat",
                f"Are you sure you want to delete '{cur_title}'?\nThis cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                if hasattr(self.store, "delete_conversation"):
                    self.store.delete_conversation(cid)
                self.conversation_deleted.emit(cid)
                self.refresh_conversations()

    def select_conversation(self, conv_id: int) -> None:
        """Programmatically select conversation row by ID."""
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            if not idx.data(ROLE_IS_SECTION) and idx.data(ROLE_CONV_ID) == conv_id:
                self.conv_list.setCurrentIndex(idx)
                break
