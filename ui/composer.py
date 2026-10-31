"""Composer component for Peachy desktop assistant.

Implements docs/REDESIGN.md Section 4:
- Multi-line expanding text input (44 px base up to 200 px max height).
- Enter to send, Shift+Enter for newlines, Up arrow in empty composer to edit last message.
- Paperclip attachment button with Upload Image, Snip Screen, and Paste options.
- Direct clipboard image pasting (Ctrl+V) and drag-and-drop image files.
- Up to 4 images, 20 MB total limit with toast notifications on violation.
- 56 px image thumbnail pills with dismiss (x) buttons.
- Short / Detailed answer length toggle chip.
- 32 px circular send button with 135 deg accent -> accent_2 gradient, converting to stop square while busy.
- Focus transition with accent border and subtle glow.
"""

from __future__ import annotations

import io
from typing import List, Optional

from PySide6.QtCore import (
    QByteArray,
    QBuffer,
    QEvent,
    QIODevice,
    QMimeData,
    QPoint,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFocusEvent,
    QIcon,
    QImage,
    QKeyEvent,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.components.chip import Chip
from ui.components.icons import get_svg_icon
from ui.theme import ThemeTokens, get_app_font, get_theme

MAX_ATTACHMENTS = 4
MAX_TOTAL_BYTES = 20 * 1024 * 1024  # 20 MB


class AutoExpandingTextEdit(QPlainTextEdit):
    """QPlainTextEdit that dynamically resizes between 44 px and 200 px based on document height."""

    send_requested = Signal()
    edit_last_requested = Signal()
    images_dropped = Signal(list)
    images_pasted = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFont(get_app_font(13))
        self.setPlaceholderText("Ask anything, paste an image, or drop files here…")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        self._min_height = 44
        self._max_height = 200
        self.setFixedHeight(self._min_height)
        self.textChanged.connect(self._adjust_height)

    def _adjust_height(self) -> None:
        doc_height = int(self.document().size().height())
        # Account for internal document margins
        margins = self.contentsMargins()
        total_height = doc_height + margins.top() + margins.bottom() + 14
        clamped = max(self._min_height, min(total_height, self._max_height))
        if self.height() != clamped:
            self.setFixedHeight(clamped)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Insert newline on Shift+Enter
                super().keyPressEvent(event)
                return
            # Plain Enter sends
            event.accept()
            self.send_requested.emit()
            return

        if event.key() == Qt.Key.Key_Up:
            # Up arrow in empty composer edits last message
            if not self.toPlainText().strip():
                event.accept()
                self.edit_last_requested.emit()
                return

        super().keyPressEvent(event)

    def insertFromMimeData(self, source: QMimeData) -> None:  # noqa: N802
        # Check for image paste from clipboard
        if source.hasImage():
            img_data = source.imageData()
            if isinstance(img_data, QImage):
                buf = QBuffer()
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                img_data.save(buf, "PNG")
                raw = bytes(buf.data().data())
                self.images_pasted.emit([raw])
                return
            elif isinstance(img_data, QPixmap):
                buf = QBuffer()
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                img_data.save(buf, "PNG")
                raw = bytes(buf.data().data())
                self.images_pasted.emit([raw])
                return

        # Check for file URLs in drag/drop or paste
        if source.hasUrls():
            image_bytes_list: List[bytes] = []
            valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
            for url in source.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if any(path.lower().endswith(ext) for ext in valid_exts):
                        try:
                            with open(path, "rb") as f:
                                image_bytes_list.append(f.read())
                        except Exception:
                            continue
            if image_bytes_list:
                self.images_dropped.emit(image_bytes_list)
                return

        super().insertFromMimeData(source)


class AttachmentThumbnail(QFrame):
    """56x56 px thumbnail pill for an attached image with remove (x) button."""

    removed = Signal(int)  # index

    def __init__(self, index: int, raw_bytes: bytes, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._index = index
        self._theme = theme
        self.setFixedSize(56, 56)
        self.setObjectName("attachmentThumb")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        # Image preview
        self.preview_lbl = QLabel(self)
        self.preview_lbl.setScaledContents(True)
        self.preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pix = QPixmap()
        pix.loadFromData(raw_bytes)
        if not pix.isNull():
            scaled = pix.scaled(52, 52, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.preview_lbl.setPixmap(scaled)

        layout.addWidget(self.preview_lbl)

        # Close button in top-right corner
        self.close_btn = QPushButton(self)
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setIcon(get_svg_icon("x", color="#FFFFFF", size=10))
        self.close_btn.clicked.connect(lambda: self.removed.emit(self._index))
        self.close_btn.move(38, 2)
        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QFrame#attachmentThumb {{
                background-color: {self._theme.secondary};
                border: 1px solid {self._theme.border};
                border-radius: 8px;
            }}
            QPushButton {{
                background-color: rgba(0, 0, 0, 0.65);
                border: none;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: rgba(220, 38, 38, 0.85);
            }}
        """)


class SendStopButton(QPushButton):
    """32 px button rendering 135 deg accent gradient for Send, or stop square while busy."""

    def __init__(self, theme: ThemeTokens, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme = theme
        self._is_busy: bool = False

    def set_busy(self, busy: bool) -> None:
        if self._is_busy != busy:
            self._is_busy = busy
            self.update()

    def apply_theme(self, theme: ThemeTokens) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = float(self.width())
        h = float(self.height())
        radius = 16.0

        if self._is_busy:
            # Stop button: secondary/hover background with dark square
            painter.setBrush(QColor(self._theme.elevated))
            painter.setPen(QPen(QColor(self._theme.border), 1.0))
            painter.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), 8, 8)

            # Center square
            painter.setBrush(QColor(self._theme.accent))
            painter.setPen(Qt.PenStyle.NoPen)
            sq_size = 10.0
            painter.drawRoundedRect(
                QRectF((w - sq_size) / 2.0, (h - sq_size) / 2.0, sq_size, sq_size),
                2.0,
                2.0,
            )
            painter.end()
            return

        if not self.isEnabled():
            # Flat subtle hover background when disabled
            painter.setBrush(QColor(self._theme.hover))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(0, 0, w, h))

            # Dim send icon
            icon_pix = get_svg_icon("send", color=self._theme.text_tertiary, size=16).pixmap(16, 16)
            painter.drawPixmap(int((w - 16) / 2), int((h - 16) / 2), icon_pix)
            painter.end()
            return

        # Active: 135 deg accent -> accent_2 gradient
        grad = QLinearGradient(0, 0, w, h)
        grad.setColorAt(0.0, QColor(self._theme.accent))
        grad.setColorAt(1.0, QColor(self._theme.accent_2))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(0, 0, w, h))

        # Send icon in accent_ink
        icon_pix = get_svg_icon("send", color=self._theme.accent_ink, size=16).pixmap(16, 16)
        painter.drawPixmap(int((w - 16) / 2), int((h - 16) / 2), icon_pix)
        painter.end()


class Composer(QFrame):
    """Centralized message input composer widget."""

    send_requested = Signal(str, list)   # text, [image_bytes]
    stop_requested = Signal()
    snip_requested = Signal()
    answer_length_changed = Signal(str)  # "short" | "detailed"
    edit_last_requested = Signal()
    toast_requested = Signal(str)

    def __init__(self, theme: Optional[ThemeTokens] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._theme = theme or get_theme()
        self._attachments: List[bytes] = []
        self._answer_length: str = "short"
        self._is_busy: bool = False
        self._is_focused: bool = False

        self.setObjectName("composerCard")
        self.setAcceptDrops(True)

        self._build_ui()
        self._apply_theme()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(6)

        # 1. Attachments Tray (hidden by default)
        self.attachments_tray = QWidget(self)
        self.attachments_layout = QHBoxLayout(self.attachments_tray)
        self.attachments_layout.setContentsMargins(0, 0, 0, 0)
        self.attachments_layout.setSpacing(8)
        self.attachments_layout.addStretch()
        self.attachments_tray.setVisible(False)
        main_layout.addWidget(self.attachments_tray)

        # 2. Text Input Area
        self.input_edit = AutoExpandingTextEdit(self)
        self.input_edit.send_requested.connect(self._on_send_clicked)
        self.input_edit.edit_last_requested.connect(self.edit_last_requested.emit)
        self.input_edit.images_dropped.connect(self.add_images)
        self.input_edit.images_pasted.connect(self.add_images)
        self.input_edit.textChanged.connect(self._update_send_state)
        main_layout.addWidget(self.input_edit)

        # 3. Action Toolbar (Bottom Row)
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setContentsMargins(0, 2, 0, 0)
        toolbar_layout.setSpacing(8)

        # Left: Attach Button with dropdown menu
        self.attach_btn = QToolButton(self)
        self.attach_btn.setFixedSize(30, 30)
        self.attach_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._attach_menu = QMenu(self.attach_btn)
        act_upload = self._attach_menu.addAction("Upload image…")
        act_upload.triggered.connect(self._on_upload_clicked)
        act_snip = self._attach_menu.addAction("Snip screen")
        act_snip.triggered.connect(self.snip_requested.emit)
        act_paste = self._attach_menu.addAction("Paste image")
        act_paste.triggered.connect(self._on_paste_clicked)
        self.attach_btn.setMenu(self._attach_menu)
        toolbar_layout.addWidget(self.attach_btn)

        toolbar_layout.addStretch()

        # Right: Short/Detailed answer length chip
        self.length_chip = Chip(
            text="Short",
            icon_name=None,
            selected=False,
            checkable=True,
            theme=self._theme,
            parent=self,
        )
        self.length_chip.setToolTip("Toggle answer conciseness (Short vs Detailed)")
        self.length_chip.clicked.connect(self._toggle_answer_length)
        toolbar_layout.addWidget(self.length_chip)

        # Right: Send/Stop Button
        self.send_btn = SendStopButton(self._theme, self)
        self.send_btn.clicked.connect(self._on_send_stop_clicked)
        toolbar_layout.addWidget(self.send_btn)

        main_layout.addLayout(toolbar_layout)
        self._update_send_state()

    def apply_theme(self, theme: ThemeTokens) -> None:
        """Update composer theme and styles dynamically."""
        self._theme = theme
        self.input_edit.setFont(get_app_font(13))
        self.length_chip.apply_theme(theme)
        self.send_btn.apply_theme(theme)
        self._apply_theme()
        # Re-apply styles on all thumbnails
        for i in range(self.attachments_layout.count() - 1):
            item = self.attachments_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), AttachmentThumbnail):
                item.widget()._theme = theme
                item.widget()._apply_style()

    def _apply_theme(self) -> None:
        t = self._theme
        border_col = t.accent if self._is_focused else t.border
        glow_shadow = f"border: 1.5px solid {border_col};"

        self.setStyleSheet(f"""
            QFrame#composerCard {{
                background-color: {t.surface};
                {glow_shadow}
                border-radius: 14px;
            }}
            QPlainTextEdit {{
                background-color: transparent;
                color: {t.text};
                border: none;
                font-family: 'Inter', 'Segoe UI Variable Text', sans-serif;
                font-size: 13px;
                line-height: 1.45;
                selection-background-color: {t.accent};
                selection-color: {t.accent_ink};
            }}
            QToolButton {{
                background-color: transparent;
                border: none;
                border-radius: 6px;
                padding: 4px;
            }}
            QToolButton:hover {{
                background-color: {t.hover};
            }}
            QToolButton::menu-indicator {{
                image: none;
            }}
            QMenu {{
                background-color: {t.elevated};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                color: {t.text};
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
            }}
            QMenu::item:selected {{
                background-color: {t.hover};
                color: {t.accent};
            }}
        """)
        self.attach_btn.setIcon(get_svg_icon("paperclip", color=t.text_secondary, size=16))

    def set_status(self, is_busy: bool) -> None:
        """Update busy status (turns send button into stop square)."""
        self._is_busy = is_busy
        self.send_btn.set_busy(is_busy)
        self._update_send_state()

    def set_answer_length(self, length: str) -> None:
        """Update answer length mode ('short' or 'detailed')."""
        self._answer_length = "detailed" if length == "detailed" else "short"
        self.length_chip.setText("Detailed" if self._answer_length == "detailed" else "Short")
        self.length_chip.setChecked(self._answer_length == "detailed")

    def _toggle_answer_length(self) -> None:
        new_len = "detailed" if self._answer_length == "short" else "short"
        self.set_answer_length(new_len)
        self.answer_length_changed.emit(self._answer_length)

    def _update_send_state(self) -> None:
        if self._is_busy:
            self.send_btn.setEnabled(True)
            return

        has_text = bool(self.input_edit.toPlainText().strip())
        has_images = len(self._attachments) > 0
        self.send_btn.setEnabled(has_text or has_images)

    def _on_send_stop_clicked(self) -> None:
        if self._is_busy:
            self.stop_requested.emit()
        else:
            self._on_send_clicked()

    def _on_send_clicked(self) -> None:
        text = self.input_edit.toPlainText().strip()
        if not text and not self._attachments:
            return

        images = list(self._attachments)
        # Clear input and attachments
        self.input_edit.clear()
        self.clear_attachments()
        self.send_requested.emit(text, images)

    def _on_upload_clicked(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images to Attach",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*.*)",
        )
        if files:
            image_bytes_list: List[bytes] = []
            for path in files:
                try:
                    with open(path, "rb") as f:
                        image_bytes_list.append(f.read())
                except Exception:
                    continue
            if image_bytes_list:
                self.add_images(image_bytes_list)

    def _on_paste_clicked(self) -> None:
        from PySide6.QtGui import QGuiApplication
        clipboard = QGuiApplication.clipboard()
        mime = clipboard.mimeData()
        if mime and mime.hasImage():
            img = clipboard.image()
            if not img.isNull():
                buf = QBuffer()
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                img.save(buf, "PNG")
                self.add_images([bytes(buf.data().data())])
        elif mime and mime.hasUrls():
            self.input_edit.insertFromMimeData(mime)

    def add_images(self, image_bytes_list: List[bytes]) -> None:
        """Add images respecting limits (max 4 images, max 20 MB total)."""
        current_count = len(self._attachments)
        current_bytes = sum(len(b) for b in self._attachments)

        for raw in image_bytes_list:
            if not raw:
                continue
            if current_count >= MAX_ATTACHMENTS:
                self.toast_requested.emit(f"Maximum {MAX_ATTACHMENTS} images allowed per message")
                break
            if current_bytes + len(raw) > MAX_TOTAL_BYTES:
                self.toast_requested.emit("Images exceed 20 MB total limit")
                break

            self._attachments.append(raw)
            current_count += 1
            current_bytes += len(raw)

        self._refresh_attachments_ui()
        self._update_send_state()

    def remove_image(self, index: int) -> None:
        """Remove attachment by index."""
        if 0 <= index < len(self._attachments):
            self._attachments.pop(index)
            self._refresh_attachments_ui()
            self._update_send_state()

    def clear_attachments(self) -> None:
        """Remove all attachments."""
        self._attachments.clear()
        self._refresh_attachments_ui()
        self._update_send_state()

    def _refresh_attachments_ui(self) -> None:
        # Clear existing widgets from tray (except stretch)
        while self.attachments_layout.count() > 1:
            item = self.attachments_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for idx, img_bytes in enumerate(self._attachments):
            thumb = AttachmentThumbnail(idx, img_bytes, self._theme, self.attachments_tray)
            thumb.removed.connect(self.remove_image)
            self.attachments_layout.insertWidget(idx, thumb)

        has_attachments = len(self._attachments) > 0
        self.attachments_tray.setVisible(has_attachments)

    # Drag and drop support directly on composer
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime.hasImage():
            img = mime.imageData()
            if isinstance(img, QImage):
                buf = QBuffer()
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                img.save(buf, "PNG")
                self.add_images([bytes(buf.data().data())])
                event.acceptProposedAction()
                return
        if mime.hasUrls():
            image_bytes_list: List[bytes] = []
            valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
            for url in mime.urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    if any(path.lower().endswith(ext) for ext in valid_exts):
                        try:
                            with open(path, "rb") as f:
                                image_bytes_list.append(f.read())
                        except Exception:
                            continue
            if image_bytes_list:
                self.add_images(image_bytes_list)
                event.acceptProposedAction()
                return

        super().dropEvent(event)
