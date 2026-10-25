"""Peachy Chat History Window.

Features:
- Visual identity matching Peachy theme tokens (light and dark mode, soft pink accents).
- Left sidebar: search box (SQL LIKE over message text), grouped by Today, Yesterday, Earlier.
- Right pane: full transcript with markdown rendered and Copy button on each answer.
- Buttons: Continue this chat, Export to Markdown, Delete chat (confirm), Clear all (confirm).
- Empty state: friendly message when there is no history or saving is off, with a link/button to Settings.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from pathlib import Path
import re
from typing import Any, List, Optional

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QIcon,
    QImage,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from config.settings import Settings, load_settings
from history.store import HistoryStore
from ui.peachy_popup import SparkleWidget
from ui.theme import ThemeTokens, get_app_font, get_theme

logger = logging.getLogger(__name__)


def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse timestamp string supporting standard ISO formats."""
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            pass
    return None


def categorize_date(dt: Optional[datetime]) -> str:
    """Categorize datetime into 'Today', 'Yesterday', or 'Earlier'."""
    if not dt:
        return "Earlier"
    today = date.today()
    msg_date = dt.date()
    if msg_date == today:
        return "Today"
    elif msg_date == today - timedelta(days=1):
        return "Yesterday"
    return "Earlier"


class HistoryWindow(QDialog):
    """The Peachy Chat History window."""

    continue_chat_requested = Signal(int)  # conversation_id
    open_settings_requested = Signal()

    def __init__(
        self,
        store: Optional[HistoryStore] = None,
        settings: Optional[Settings] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.store = store or HistoryStore()
        self.settings = settings or load_settings()
        self.theme = get_theme()

        self._selected_conversation_id: Optional[int] = None
        self._copy_timers: List[QTimer] = []

        self._init_window()
        self._build_ui()
        self.reload_history()

    def _init_window(self) -> None:
        self.setWindowTitle("Peachy - Chat History")
        self.setMinimumSize(780, 520)
        self.resize(840, 580)
        self.setStyleSheet(self._generate_stylesheet())

    def _generate_stylesheet(self) -> str:
        t = self.theme
        return f"""
        QDialog {{
            background-color: {t.card};
            color: {t.text};
        }}
        QLabel {{
            color: {t.text};
        }}
        QLineEdit {{
            border: 1px solid {t.border};
            border-radius: 8px;
            padding: 6px 10px;
            background-color: {t.surface};
            color: {t.text};
            font-size: 13px;
        }}
        QLineEdit:focus {{
            border: 1.5px solid {t.accent};
        }}
        QPushButton#primaryButton {{
            background-color: {t.accent};
            color: #FFFFFF;
            border-radius: 8px;
            padding: 6px 14px;
            font-weight: 600;
            border: none;
        }}
        QPushButton#primaryButton:hover {{
            background-color: {t.accent_hover};
        }}
        QPushButton#secondaryButton {{
            background-color: {t.surface};
            color: {t.text};
            border: 1px solid {t.border};
            border-radius: 8px;
            padding: 5px 12px;
        }}
        QPushButton#secondaryButton:hover {{
            border-color: {t.accent};
            background-color: {t.soft_surface};
        }}
        QTreeWidget {{
            border: 1px solid {t.border};
            border-radius: 10px;
            background-color: {t.card};
            outline: none;
        }}
        QTreeWidget::item {{
            padding: 6px 8px;
            border-radius: 6px;
        }}
        QTreeWidget::item:hover {{
            background-color: {t.soft_surface};
        }}
        QTreeWidget::item:selected {{
            background-color: {t.soft_surface};
            color: {t.accent};
            font-weight: 600;
        }}
        QScrollBar:vertical {{
            width: 8px;
            background: transparent;
        }}
        QScrollBar::handle:vertical {{
            background: {t.border};
            border-radius: 4px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {t.accent};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        """

    def _build_ui(self) -> None:
        t = self.theme
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 14, 16, 14)
        main_layout.setSpacing(10)

        # Header bar
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.sparkle_icon = SparkleWidget(size=22, parent=self)
        header_layout.addWidget(self.sparkle_icon)

        title_label = QLabel("peachy history")
        title_label.setFont(get_app_font(16, bold=True))
        title_label.setStyleSheet(f"color: {t.accent};")
        header_layout.addWidget(title_label)

        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Splitter dividing Sidebar and Transcript Pane
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setHandleWidth(8)

        # 1. Left Sidebar
        sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(8)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search chats (SQL LIKE)...")
        self.search_input.textChanged.connect(self._on_search_changed)
        sidebar_layout.addWidget(self.search_input)

        # Grouped Tree Widget
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setColumnCount(2)
        self.tree_widget.setColumnWidth(0, 180)
        self.tree_widget.itemClicked.connect(self._on_tree_item_clicked)
        sidebar_layout.addWidget(self.tree_widget)

        # Bottom clear all button
        sidebar_bottom = QHBoxLayout()
        self.clear_all_btn = QPushButton("Clear all")
        self.clear_all_btn.setObjectName("secondaryButton")
        self.clear_all_btn.setFont(get_app_font(11))
        self.clear_all_btn.setToolTip("Delete all chat history permanently")
        self.clear_all_btn.clicked.connect(self._on_clear_all)
        sidebar_bottom.addWidget(self.clear_all_btn)
        sidebar_bottom.addStretch()
        sidebar_layout.addLayout(sidebar_bottom)

        sidebar_widget.setMinimumWidth(260)
        sidebar_widget.setMaximumWidth(360)
        splitter.addWidget(sidebar_widget)

        # 2. Right Pane (Stacked Widget for empty vs transcript view)
        self.right_stack = QStackedWidget()

        # View 0: Empty State
        self.empty_widget = self._build_empty_widget()
        self.right_stack.addWidget(self.empty_widget)

        # View 1: Transcript View
        self.transcript_widget = self._build_transcript_widget()
        self.right_stack.addWidget(self.transcript_widget)

        splitter.addWidget(self.right_stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter)

    def _build_empty_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        sparkle = SparkleWidget(size=36, parent=widget)
        layout.addWidget(sparkle, alignment=Qt.AlignmentFlag.AlignCenter)

        self.empty_title_label = QLabel("No chat history yet")
        self.empty_title_label.setFont(get_app_font(14, bold=True))
        self.empty_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_title_label)

        self.empty_subtitle_label = QLabel("Chats will appear here after they complete.")
        self.empty_subtitle_label.setFont(get_app_font(12))
        self.empty_subtitle_label.setStyleSheet(f"color: {self.theme.muted};")
        self.empty_subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_subtitle_label)

        self.open_settings_btn = QPushButton("Open Settings")
        self.open_settings_btn.setObjectName("secondaryButton")
        self.open_settings_btn.setFont(get_app_font(12))
        self.open_settings_btn.clicked.connect(self._on_open_settings)
        layout.addWidget(self.open_settings_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        return widget

    def _build_transcript_widget(self) -> QWidget:
        t = self.theme
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(8)

        # Top Action Bar
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        self.conv_title_label = QLabel("")
        self.conv_title_label.setFont(get_app_font(14, bold=True))
        self.conv_title_label.setStyleSheet(f"color: {t.accent};")
        self.conv_date_label = QLabel("")
        self.conv_date_label.setFont(get_app_font(11))
        self.conv_date_label.setStyleSheet(f"color: {t.muted};")
        info_layout.addWidget(self.conv_title_label)
        info_layout.addWidget(self.conv_date_label)
        top_bar.addLayout(info_layout)
        top_bar.addStretch()

        self.continue_btn = QPushButton("Continue this chat")
        self.continue_btn.setObjectName("primaryButton")
        self.continue_btn.setFont(get_app_font(12, bold=True))
        self.continue_btn.setToolTip("Open popup with this conversation loaded to ask follow-up questions")
        self.continue_btn.clicked.connect(self._on_continue_chat)

        self.export_btn = QPushButton("Export to Markdown")
        self.export_btn.setObjectName("secondaryButton")
        self.export_btn.setFont(get_app_font(11))
        self.export_btn.clicked.connect(self._on_export_markdown)

        self.delete_btn = QPushButton("Delete chat")
        self.delete_btn.setObjectName("secondaryButton")
        self.delete_btn.setFont(get_app_font(11))
        self.delete_btn.clicked.connect(self._on_delete_chat)

        top_bar.addWidget(self.continue_btn)
        top_bar.addWidget(self.export_btn)
        top_bar.addWidget(self.delete_btn)
        layout.addLayout(top_bar)

        # Scroll Area for Transcript messages
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet(f"background-color: {t.card};")

        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(0, 8, 8, 8)
        self.messages_layout.setSpacing(12)
        self.messages_layout.addStretch()
        self.scroll_area.setWidget(self.messages_container)
        layout.addWidget(self.scroll_area)

        # Contextual footnote note
        self.note_label = QLabel("Earlier screenshots are not re-sent. Select a new area with New Screenshot to add a fresh image.")
        self.note_label.setFont(get_app_font(11))
        self.note_label.setStyleSheet(f"color: {t.muted}; font-style: italic;")
        layout.addWidget(self.note_label)

        return widget

    def reload_history(self, search_text: str = "") -> None:
        """Populate tree list grouped by Today, Yesterday, Earlier."""
        self.tree_widget.clear()
        self.settings = load_settings()

        conversations = self.store.list_conversations(query=search_text)

        if not conversations:
            self.right_stack.setCurrentIndex(0)
            if not getattr(self.settings, "save_history", False):
                self.empty_title_label.setText("Chat history is turned off")
                self.empty_subtitle_label.setText("Enable 'Save chat history locally' in Settings to save your chats.")
            else:
                self.empty_title_label.setText("No chat history yet")
                self.empty_subtitle_label.setText("Your completed answers will be saved here on this PC.")
            return

        # Group conversations into Today, Yesterday, Earlier
        groups: dict[str, List[dict[str, Any]]] = {
            "Today": [],
            "Yesterday": [],
            "Earlier": [],
        }

        for conv in conversations:
            dt = parse_timestamp(conv.get("updated_at") or conv.get("created_at") or "")
            category = categorize_date(dt)
            groups[category].append(conv)

        # Build tree items
        for group_name in ("Today", "Yesterday", "Earlier"):
            convs = groups[group_name]
            if not convs:
                continue

            header_item = QTreeWidgetItem(self.tree_widget)
            header_item.setText(0, group_name)
            header_item.setFont(0, get_app_font(12, bold=True))
            header_item.setForeground(0, QColor(self.theme.accent))
            header_item.setFlags(Qt.ItemFlag.NoItemFlags)
            header_item.setExpanded(True)

            for conv in convs:
                item = QTreeWidgetItem(header_item)
                item.setText(0, conv["title"])
                dt = parse_timestamp(conv.get("updated_at") or "")
                time_str = dt.strftime("%H:%M") if dt else ""
                item.setText(1, time_str)
                item.setFont(0, get_app_font(12))
                item.setFont(1, get_app_font(11))
                item.setForeground(1, QColor(self.theme.muted))
                item.setData(0, Qt.ItemDataRole.UserRole, conv["id"])

                # Optional 240px thumbnail preview icon
                thumb_bytes = conv.get("thumbnail")
                if thumb_bytes:
                    qimg = QImage.fromData(thumb_bytes)
                    if not qimg.isNull():
                        pixmap = QPixmap.fromImage(qimg).scaled(
                            28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                        )
                        item.setIcon(0, QIcon(pixmap))

        # Select first conversation or re-select previous
        target_item = self._find_item_by_id(self._selected_conversation_id)
        if target_item is not None:
            self.tree_widget.setCurrentItem(target_item)
            self._load_conversation_transcript(self._selected_conversation_id)
        else:
            # Select first available conversation item
            first_child = self._find_first_conversation_item()
            if first_child is not None:
                self.tree_widget.setCurrentItem(first_child)
                conv_id = first_child.data(0, Qt.ItemDataRole.UserRole)
                self._load_conversation_transcript(conv_id)
            else:
                self.right_stack.setCurrentIndex(0)

    def _find_first_conversation_item(self) -> Optional[QTreeWidgetItem]:
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            if group.childCount() > 0:
                return group.child(0)
        return None

    def _find_item_by_id(self, conv_id: Optional[int]) -> Optional[QTreeWidgetItem]:
        if conv_id is None:
            return None
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if child.data(0, Qt.ItemDataRole.UserRole) == conv_id:
                    return child
        return None

    def _on_search_changed(self, text: str) -> None:
        self.reload_history(search_text=text)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        conv_id = item.data(0, Qt.ItemDataRole.UserRole)
        if conv_id is not None:
            self._load_conversation_transcript(conv_id)

    def _load_conversation_transcript(self, conversation_id: int) -> None:
        self._selected_conversation_id = conversation_id
        conv = self.store.get_conversation(conversation_id)
        if not conv:
            self.right_stack.setCurrentIndex(0)
            return

        self.conv_title_label.setText(conv["title"])
        self.conv_date_label.setText(f"Last updated: {conv['updated_at']}")

        # Clear existing message widgets
        while self.messages_layout.count() > 1:
            child = self.messages_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        messages = self.store.get_messages(conversation_id)
        t = self.theme

        for msg in messages:
            role = msg.get("role", "user")
            text = msg.get("text", "")
            created_at = msg.get("created_at", "")

            msg_card = QFrame()
            card_layout = QVBoxLayout(msg_card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(6)

            if role == "user":
                msg_card.setStyleSheet(f"""
                    QFrame {{
                        background-color: {t.surface};
                        border: 1px solid {t.border};
                        border-radius: 10px;
                    }}
                """)
                hdr = QHBoxLayout()
                hdr_label = QLabel("You")
                hdr_label.setFont(get_app_font(12, bold=True))
                hdr_label.setStyleSheet(f"color: {t.muted};")
                hdr.addWidget(hdr_label)
                hdr.addStretch()
                time_lbl = QLabel(created_at)
                time_lbl.setFont(get_app_font(10))
                time_lbl.setStyleSheet(f"color: {t.muted};")
                hdr.addWidget(time_lbl)
                card_layout.addLayout(hdr)

                body = QLabel(text)
                body.setWordWrap(True)
                body.setFont(get_app_font(13))
                body.setStyleSheet(f"color: {t.text};")
                card_layout.addWidget(body)

            else:  # model / assistant
                msg_card.setStyleSheet(f"""
                    QFrame {{
                        background-color: {t.card};
                        border: 1px solid {t.accent};
                        border-radius: 10px;
                    }}
                """)
                hdr = QHBoxLayout()
                sparkle = SparkleWidget(size=16, parent=msg_card)
                hdr.addWidget(sparkle)
                hdr_label = QLabel("Peachy")
                hdr_label.setFont(get_app_font(12, bold=True))
                hdr_label.setStyleSheet(f"color: {t.accent};")
                hdr.addWidget(hdr_label)
                hdr.addStretch()

                # Copy button on each answer
                copy_btn = QPushButton("Copy")
                copy_btn.setObjectName("secondaryButton")
                copy_btn.setFont(get_app_font(11))
                copy_btn.setToolTip("Copy this answer to clipboard")
                copy_btn.clicked.connect(self._create_copy_handler(copy_btn, text))
                hdr.addWidget(copy_btn)
                card_layout.addLayout(hdr)

                # Markdown text browser with code styling
                browser = QTextBrowser()
                browser.setOpenExternalLinks(True)
                browser.setFont(get_app_font(13))
                browser.setFrameShape(QFrame.Shape.NoFrame)
                browser.setStyleSheet("background: transparent;")
                browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

                doc = browser.document()
                doc.setDefaultStyleSheet(f"""
                    pre {{
                        background-color: {t.code_bg};
                        border: 1px solid {t.border};
                        border-radius: 6px;
                        padding: 8px;
                        font-family: Consolas, 'Courier New', monospace;
                        font-size: 12px;
                        color: {t.text};
                    }}
                    code {{
                        background-color: {t.code_bg};
                        border-radius: 4px;
                        padding: 2px 4px;
                        font-family: Consolas, 'Courier New', monospace;
                        font-size: 12px;
                        color: {t.text};
                    }}
                    p {{ margin-bottom: 6px; }}
                    ul, ol {{ margin-left: 16px; margin-bottom: 6px; }}
                """)
                browser.setMarkdown(text)
                card_layout.addWidget(browser)

            # Insert before the bottom stretch
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, msg_card)

        self.right_stack.setCurrentIndex(1)

    def _create_copy_handler(self, btn: QPushButton, text: str) -> Any:
        def handler() -> None:
            clipboard = QGuiApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
            btn.setText("Copied!")
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: btn.setText("Copy"))
            timer.start(1500)
            self._copy_timers.append(timer)

        return handler

    def _on_continue_chat(self) -> None:
        if self._selected_conversation_id is None:
            return
        conv_id = self._selected_conversation_id
        self.hide()
        self.continue_chat_requested.emit(conv_id)

    def _on_export_markdown(self) -> None:
        if self._selected_conversation_id is None:
            return
        conv = self.store.get_conversation(self._selected_conversation_id)
        if not conv:
            return

        # Sanitize filename
        clean_title = re.sub(r'[\\/*?:"<>|]', "", conv["title"]).strip() or "conversation"
        clean_title = clean_title[:40].strip()

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Chat to Markdown",
            f"{clean_title}.md",
            "Markdown (*.md);;All Files (*)",
        )
        if not file_path:
            return

        markdown_content = self.store.export_markdown(self._selected_conversation_id)
        try:
            Path(file_path).write_text(markdown_content, encoding="utf-8")
            QMessageBox.information(self, "Export Successful", f"Conversation exported to:\n{file_path}")
        except Exception as exc:
            logger.exception("Failed to export markdown: %s", exc)
            QMessageBox.warning(self, "Export Error", f"Could not save file: {exc}")

    def _on_delete_chat(self) -> None:
        if self._selected_conversation_id is None:
            return

        reply = QMessageBox.question(
            self,
            "Delete Chat",
            "Are you sure you want to delete this chat conversation? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.delete_conversation(self._selected_conversation_id)
            self._selected_conversation_id = None
            self.reload_history(self.search_input.text().strip())

    def _on_clear_all(self) -> None:
        reply = QMessageBox.question(
            self,
            "Clear All History",
            "Are you sure you want to delete all saved conversations? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.clear_all()
            self._selected_conversation_id = None
            self.reload_history()

    def _on_open_settings(self) -> None:
        self.hide()
        self.open_settings_requested.emit()

    def refresh_and_show(self) -> None:
        """Reload data and show window."""
        self.reload_history(self.search_input.text().strip())
        self.show()
        self.raise_()
        self.activateWindow()

    def refresh(self) -> None:
        """Alias for reload_history."""
        self.reload_history(self.search_input.text().strip())

    @property
    def tree(self) -> QTreeWidget:
        return self.tree_widget

    @property
    def search_edit(self) -> QLineEdit:
        return self.search_input

    @property
    def btn_continue(self) -> QPushButton:
        return self.continue_btn

    @property
    def btn_delete(self) -> QPushButton:
        return self.delete_btn

    @property
    def btn_clear_all(self) -> QPushButton:
        return self.clear_all_btn

    @property
    def empty_state(self) -> QWidget:
        return self.empty_widget
