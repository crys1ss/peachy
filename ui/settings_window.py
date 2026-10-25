"""Peachy Settings Window.

Features:
- Visual identity matching Peachy theme tokens (light/dark mode, 16px radius, soft pink accents).
- Interactive 'click to record' shortcut recorder with inline conflict detection.
- Double-tap C configuration: toggle, 200-500ms slider, warning text.
- AI Configuration: masked API key field, inline Test button with non-blocking check, model dropdown with custom fallback.
- Popup preferences: pinned by default toggle, position (near selection vs last used).
- Windows startup launch toggle via winreg.
- Privacy disclosure card.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

from PySide6.QtCore import QObject, QRect, QSize, Qt, QThread, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ai.gemini_provider import test_connection
from config import key_storage
from config.settings import (
    Settings,
    is_launch_at_startup_enabled,
    load_settings,
    save_settings,
    set_launch_at_startup,
)
from core.hotkey_manager import parse_shortcut
from history.store import HistoryStore
from ui import theme

logger = logging.getLogger(__name__)

AVAILABLE_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-flash-lite-latest",
]


class ShortcutRecorderButton(QPushButton):
    """Button that intercepts key combinations to record a global shortcut."""

    shortcut_recorded = Signal(str)

    def __init__(self, current_shortcut: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_shortcut = current_shortcut
        self.is_recording = False
        self._update_text()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._toggle_recording)

    def set_shortcut(self, shortcut: str) -> None:
        self.current_shortcut = shortcut
        self.is_recording = False
        self._update_text()

    def _update_text(self) -> None:
        if self.is_recording:
            self.setText("Press keys (or Esc to cancel)...")
        else:
            self.setText(self.current_shortcut)

    def _toggle_recording(self) -> None:
        self.is_recording = not self.is_recording
        self._update_text()
        if self.is_recording:
            self.setFocus()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.is_recording:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.is_recording = False
            self._update_text()
            return

        # Ignore modifier-only presses
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
        ):
            return

        modifiers = event.modifiers()
        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("Win")

        # Map key
        key_str = self._key_to_string(key)
        if not key_str:
            return

        parts.append(key_str)
        recorded = "+".join(parts)

        try:
            parse_shortcut(recorded)
            self.current_shortcut = recorded
            self.is_recording = False
            self._update_text()
            self.shortcut_recorded.emit(recorded)
        except ValueError:
            self.setText(f"Invalid ({recorded}) - press again")

    def _key_to_string(self, key: int) -> Optional[str]:
        if key == Qt.Key.Key_Space:
            return "Space"
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            return f"F{key - Qt.Key.Key_F1 + 1}"
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return chr(key)
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            return chr(key)
        return None

    def focusOutEvent(self, event) -> None:
        if self.is_recording:
            self.is_recording = False
            self._update_text()
        super().focusOutEvent(event)


class ApiKeyTesterThread(QThread):
    """Worker thread testing Gemini API key without blocking UI."""

    result_ready = Signal(bool, str)

    def __init__(self, api_key: str, model: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.api_key = api_key
        self.model = model

    def run(self) -> None:
        success, msg = test_connection(api_key=self.api_key, model=self.model)
        self.result_ready.emit(success, msg)


class SettingsWindow(QDialog):
    """Settings dialog styled according to Peachy design specifications."""

    settings_applied = Signal(Settings)

    def __init__(
        self,
        settings: Optional[Settings] = None,
        hotkey_manager: Optional[Any] = None,
        double_tap_hook: Optional[Any] = None,
        store: Optional[HistoryStore] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.settings = settings or load_settings()
        self.hotkey_manager = hotkey_manager
        self.double_tap_hook = double_tap_hook
        self.store = store or HistoryStore()
        self.theme_tokens = theme.get_theme()
        self._tester_thread: Optional[ApiKeyTesterThread] = None

        self._init_window()
        self._build_ui()
        self._load_values()

    def _init_window(self) -> None:
        self.setWindowTitle("Peachy Settings")
        self.resize(480, 840)
        self.setFont(theme.get_app_font(13))
        self.setStyleSheet(self._generate_stylesheet())

    def _generate_stylesheet(self) -> str:
        t = self.theme_tokens
        return f"""
        QDialog {{
            background-color: {t.card};
            color: {t.text};
        }}
        QLabel {{
            color: {t.text};
        }}
        QGroupBox {{
            font-weight: 600;
            border: 1px solid {t.border};
            border-radius: 12px;
            margin-top: 10px;
            padding-top: 14px;
        }}
        QLineEdit, QComboBox, QPushButton {{
            border: 1px solid {t.border};
            border-radius: 8px;
            padding: 6px 10px;
            background-color: {t.card};
            color: {t.text};
            font-size: 13px;
        }}
        QLineEdit:focus, QComboBox:focus {{
            border: 1.5px solid {t.accent};
        }}
        QPushButton:hover {{
            background-color: {t.soft_surface};
            border-color: {t.accent};
        }}
        QSlider::groove:horizontal {{
            height: 6px;
            background: {t.border};
            border-radius: 3px;
        }}
        QSlider::sub-page:horizontal {{
            background: {t.accent};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {t.accent};
            width: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {t.accent_hover};
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid {t.border};
            background: {t.card};
        }}
        QCheckBox::indicator:checked {{
            background-color: {t.accent};
            border-color: {t.accent};
        }}
        """

    def _build_ui(self) -> None:
        t = self.theme_tokens
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header with mascot & title
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.title_label = QLabel("peachy settings")
        self.title_label.setFont(theme.get_app_font(16, bold=True))
        self.title_label.setStyleSheet(f"color: {t.accent};")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        # 1. Shortcut Section
        shortcut_label = QLabel("Global Shortcuts")
        shortcut_label.setFont(theme.get_app_font(13, bold=True))
        layout.addWidget(shortcut_label)

        # Capture Hotkey
        cap_lbl = QLabel("Screen Capture:")
        cap_lbl.setFont(theme.get_app_font(12))
        layout.addWidget(cap_lbl)
        sc_row = QHBoxLayout()
        self.shortcut_button = ShortcutRecorderButton(self.settings.hotkey)
        self.shortcut_button.shortcut_recorded.connect(self._on_shortcut_recorded)
        sc_row.addWidget(self.shortcut_button)
        layout.addLayout(sc_row)

        self.shortcut_status_label = QLabel("")
        self.shortcut_status_label.setStyleSheet("color: #EF4444; font-size: 11px;")
        layout.addWidget(self.shortcut_status_label)

        # History Hotkey
        hist_lbl = QLabel("Chat History:")
        hist_lbl.setFont(theme.get_app_font(12))
        layout.addWidget(hist_lbl)
        hist_sc_row = QHBoxLayout()
        self.history_shortcut_button = ShortcutRecorderButton(getattr(self.settings, "history_hotkey", "Ctrl+Shift+H"))
        self.history_shortcut_button.shortcut_recorded.connect(self._on_history_shortcut_recorded)
        hist_sc_row.addWidget(self.history_shortcut_button)
        layout.addLayout(hist_sc_row)

        self.history_shortcut_status_label = QLabel("")
        self.history_shortcut_status_label.setStyleSheet("color: #EF4444; font-size: 11px;")
        layout.addWidget(self.history_shortcut_status_label)

        # 2. Double Tap C Section
        self.double_tap_check = QCheckBox("Enable Double-tap 'C' activation")
        self.double_tap_check.toggled.connect(self._on_double_tap_toggled)
        layout.addWidget(self.double_tap_check)

        dt_layout = QHBoxLayout()
        dt_layout.setContentsMargins(20, 0, 0, 0)
        self.interval_label = QLabel(f"Interval: {self.settings.double_tap_interval_ms} ms")
        self.interval_slider = QSlider(Qt.Orientation.Horizontal)
        self.interval_slider.setRange(200, 500)
        self.interval_slider.setValue(self.settings.double_tap_interval_ms)
        self.interval_slider.valueChanged.connect(self._on_interval_changed)
        dt_layout.addWidget(self.interval_slider)
        dt_layout.addWidget(self.interval_label)
        layout.addLayout(dt_layout)

        self.warning_label = QLabel("⚠ May trigger while typing words with 'cc' (e.g. accept, success)")
        self.warning_label.setStyleSheet(f"color: {t.muted}; font-size: 11px; margin-left: 20px;")
        layout.addWidget(self.warning_label)

        # Divider
        layout.addWidget(self._create_divider())

        # 3. AI Section
        ai_title = QLabel("Gemini AI Configuration")
        ai_title.setFont(theme.get_app_font(13, bold=True))
        layout.addWidget(ai_title)

        key_row = QHBoxLayout()
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("Paste Gemini API Key (stored in Windows Credential Manager)")
        key_row.addWidget(self.key_input)

        self.toggle_eye_btn = QPushButton("👁")
        self.toggle_eye_btn.setFixedWidth(36)
        self.toggle_eye_btn.clicked.connect(self._toggle_key_visibility)
        key_row.addWidget(self.toggle_eye_btn)

        self.test_key_btn = QPushButton("Test")
        self.test_key_btn.setFixedWidth(56)
        self.test_key_btn.clicked.connect(self._test_api_key)
        key_row.addWidget(self.test_key_btn)
        layout.addLayout(key_row)

        self.key_status_label = QLabel("")
        self.key_status_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.key_status_label)

        model_row = QHBoxLayout()
        model_label = QLabel("Model:")
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        for m in AVAILABLE_MODELS:
            self.model_combo.addItem(m)
        model_row.addWidget(model_label)
        model_row.addWidget(self.model_combo, stretch=1)
        layout.addLayout(model_row)

        # Divider
        layout.addWidget(self._create_divider())

        # 4. Selection & Capture Section
        sel_title = QLabel("Selection & Capture")
        sel_title.setFont(theme.get_app_font(13, bold=True))
        layout.addWidget(sel_title)

        mode_row = QHBoxLayout()
        mode_label = QLabel("Mode:")
        self.mode_freehand = QRadioButton("Freehand (default)")
        self.mode_rect = QRadioButton("Rectangle")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.mode_freehand, 0)
        self.mode_group.addButton(self.mode_rect, 1)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.mode_freehand)
        mode_row.addWidget(self.mode_rect)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        shape_row = QHBoxLayout()
        shape_label = QLabel("Outside shape:")
        self.shape_blank = QRadioButton("Blank (white)")
        self.shape_keep = QRadioButton("Keep (bounding box)")
        self.shape_group = QButtonGroup(self)
        self.shape_group.addButton(self.shape_blank, 0)
        self.shape_group.addButton(self.shape_keep, 1)
        shape_row.addWidget(shape_label)
        shape_row.addWidget(self.shape_blank)
        shape_row.addWidget(self.shape_keep)
        shape_row.addStretch()
        layout.addLayout(shape_row)

        # Divider
        layout.addWidget(self._create_divider())

        # 5. Popup & System Section
        pref_title = QLabel("Popup & Startup Preferences")
        pref_title.setFont(theme.get_app_font(13, bold=True))
        layout.addWidget(pref_title)

        self.pinned_check = QCheckBox("Keep popup pinned on top by default")
        layout.addWidget(self.pinned_check)

        pos_row = QHBoxLayout()
        pos_label = QLabel("Position:")
        self.pos_near = QRadioButton("Near selection")
        self.pos_last = QRadioButton("Last used spot")
        self.pos_group = QButtonGroup(self)
        self.pos_group.addButton(self.pos_near, 0)
        self.pos_group.addButton(self.pos_last, 1)
        pos_row.addWidget(pos_label)
        pos_row.addWidget(self.pos_near)
        pos_row.addWidget(self.pos_last)
        pos_row.addStretch()
        layout.addLayout(pos_row)

        self.startup_check = QCheckBox("Launch Peachy at Windows startup")
        layout.addWidget(self.startup_check)

        # Divider
        layout.addWidget(self._create_divider())

        # 6. Chat History Section
        history_title = QLabel("Chat History")
        history_title.setFont(theme.get_app_font(13, bold=True))
        layout.addWidget(history_title)

        self.save_history_check = QCheckBox("Save chat history locally on this PC")
        layout.addWidget(self.save_history_check)

        self.save_thumbnails_check = QCheckBox("Save 240px thumbnails with conversations")
        self.save_thumbnails_check.setStyleSheet("margin-left: 20px;")
        layout.addWidget(self.save_thumbnails_check)

        clear_row = QHBoxLayout()
        self.clear_history_btn = QPushButton("Clear All History")
        self.clear_history_btn.setObjectName("secondaryButton")
        self.clear_history_btn.setToolTip("Delete all saved conversations and vacuum database")
        self.clear_history_btn.clicked.connect(self._on_clear_history)
        clear_row.addWidget(self.clear_history_btn)
        clear_row.addStretch()
        layout.addLayout(clear_row)

        self.clear_status_label = QLabel("")
        self.clear_status_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self.clear_status_label)

        # 7. Privacy Notice Card
        privacy_frame = QFrame()
        privacy_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {t.soft_surface};
                border: 1px solid {t.border};
                border-radius: 10px;
                padding: 6px;
            }}
        """)
        privacy_layout = QVBoxLayout(privacy_frame)
        privacy_layout.setContentsMargins(10, 8, 10, 8)
        privacy_title = QLabel("Privacy Disclosure")
        privacy_title.setFont(theme.get_app_font(11, bold=True))
        privacy_title.setStyleSheet(f"color: {t.accent};")
        privacy_text = QLabel(
            "Peachy only looks at your screen when you press the shortcut. "
            "It sends only the area you select, and only when you press Send. "
            "History stays on this PC, is never uploaded, and the selected screen area is still only sent to Gemini when I press Send."
        )
        privacy_text.setWordWrap(True)
        privacy_text.setFont(theme.get_app_font(11))
        privacy_text.setStyleSheet(f"color: {t.muted};")
        privacy_layout.addWidget(privacy_title)
        privacy_layout.addWidget(privacy_text)
        layout.addWidget(privacy_frame)

        layout.addStretch()

        # 6. Dialog Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t.accent};
                color: #FFFFFF;
                font-weight: 600;
                padding: 6px 16px;
            }}
            QPushButton:hover {{
                background-color: {t.accent_hover};
            }}
        """)
        self.save_btn.clicked.connect(self._save_and_apply)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def _create_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet(f"background-color: {self.theme_tokens.border}; max-height: 1px;")
        return line

    def _load_values(self) -> None:
        """Populate UI controls from settings and keyring."""
        # Shortcut
        self.shortcut_button.set_shortcut(self.settings.hotkey)

        # Double-tap C
        self.double_tap_check.setChecked(self.settings.double_tap_enabled)
        self.interval_slider.setValue(self.settings.double_tap_interval_ms)
        self.interval_slider.setEnabled(self.settings.double_tap_enabled)
        self.interval_label.setEnabled(self.settings.double_tap_enabled)
        self.warning_label.setEnabled(self.settings.double_tap_enabled)

        # API key from keyring/env
        key = key_storage.get_api_key()
        if key:
            self.key_input.setText(key)
            src = key_storage.get_key_source()
            if src == "keyring":
                self.key_status_label.setText("✓ Loaded from Windows Credential Manager")
                self.key_status_label.setStyleSheet("color: #10B981; font-size: 11px;")
            elif src == "environment":
                self.key_status_label.setText("ℹ Loaded from GEMINI_API_KEY environment variable")
                self.key_status_label.setStyleSheet(f"color: {self.theme_tokens.muted}; font-size: 11px;")

        # Model
        idx = self.model_combo.findText(self.settings.model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
        else:
            self.model_combo.setEditText(self.settings.model)

        # Selection preferences
        if getattr(self.settings, "selection_mode", "freehand") == "rectangle":
            self.mode_rect.setChecked(True)
        else:
            self.mode_freehand.setChecked(True)

        if getattr(self.settings, "outside_shape", "blank") == "keep":
            self.shape_keep.setChecked(True)
        else:
            self.shape_blank.setChecked(True)

        # Popup preferences
        self.pinned_check.setChecked(self.settings.pinned)
        if getattr(self.settings, "popup_position", "near_selection") == "last_used":
            self.pos_last.setChecked(True)
        else:
            self.pos_near.setChecked(True)

        # Windows Startup
        self.startup_check.setChecked(is_launch_at_startup_enabled())

        # History settings
        self.history_shortcut_button.set_shortcut(getattr(self.settings, "history_hotkey", "Ctrl+Shift+H"))
        self.save_history_check.setChecked(getattr(self.settings, "save_history", False))
        self.save_thumbnails_check.setChecked(getattr(self.settings, "save_thumbnails", False))
        self.save_thumbnails_check.setEnabled(getattr(self.settings, "save_history", False))
        self.save_history_check.toggled.connect(self.save_thumbnails_check.setEnabled)

    def _toggle_key_visibility(self) -> None:
        if self.key_input.echoMode() == QLineEdit.EchoMode.Password:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self.toggle_eye_btn.setText("🔒")
        else:
            self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
            self.toggle_eye_btn.setText("👁")

    def _on_shortcut_recorded(self, new_shortcut: str) -> None:
        self.shortcut_status_label.setText("")

    def _on_history_shortcut_recorded(self, new_shortcut: str) -> None:
        self.history_shortcut_status_label.setText("")

    def _on_clear_history(self) -> None:
        reply = QMessageBox.question(
            self,
            "Clear All History",
            "Are you sure you want to delete all chat history? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.store.clear_all()
            self.clear_status_label.setText("✓ All chat history deleted.")
            self.clear_status_label.setStyleSheet("color: #10B981; font-size: 11px;")

    def _on_double_tap_toggled(self, checked: bool) -> None:
        self.interval_slider.setEnabled(checked)
        self.interval_label.setEnabled(checked)
        self.warning_label.setEnabled(checked)

    def _on_interval_changed(self, val: int) -> None:
        self.interval_label.setText(f"Interval: {val} ms")

    def _test_api_key(self) -> None:
        key = self.key_input.text().strip()
        model = self.model_combo.currentText().strip()
        if not key:
            self.key_status_label.setText("Please enter an API key to test.")
            self.key_status_label.setStyleSheet("color: #EF4444; font-size: 11px;")
            return

        self.test_key_btn.setEnabled(False)
        self.key_status_label.setText("Testing API key...")
        self.key_status_label.setStyleSheet(f"color: {self.theme_tokens.muted}; font-size: 11px;")

        self._tester_thread = ApiKeyTesterThread(api_key=key, model=model, parent=self)
        self._tester_thread.result_ready.connect(self._on_test_result)
        self._tester_thread.start()

    def _on_test_result(self, success: bool, message: str) -> None:
        self.test_key_btn.setEnabled(True)
        if success:
            self.key_status_label.setText(f"✓ {message}")
            self.key_status_label.setStyleSheet("color: #10B981; font-size: 11px;")
        else:
            self.key_status_label.setText(f"✗ {message}")
            self.key_status_label.setStyleSheet("color: #EF4444; font-size: 11px;")

    def _save_and_apply(self) -> None:
        """Validate, register new shortcut, persist settings, and apply without restart."""
        new_shortcut = self.shortcut_button.current_shortcut.strip()
        old_shortcut = self.settings.hotkey

        # Try to register shortcut if changed and manager is available
        if self.hotkey_manager and new_shortcut != old_shortcut:
            registered = self.hotkey_manager.register(new_shortcut)
            if not registered:
                self.shortcut_status_label.setText(
                    f"Conflict: '{new_shortcut}' is already in use by another app. Kept '{old_shortcut}'."
                )
                self.shortcut_button.set_shortcut(old_shortcut)
                return
            else:
                self.settings.hotkey = new_shortcut
        else:
            self.settings.hotkey = new_shortcut

        # Try to register history shortcut if changed and manager supports it
        new_hist_shortcut = self.history_shortcut_button.current_shortcut.strip()
        old_hist_shortcut = getattr(self.settings, "history_hotkey", "Ctrl+Shift+H")

        if (
            self.hotkey_manager
            and hasattr(self.hotkey_manager, "register_history")
            and new_hist_shortcut != old_hist_shortcut
        ):
            hist_registered = self.hotkey_manager.register_history(new_hist_shortcut)
            if not hist_registered:
                self.history_shortcut_status_label.setText(
                    f"Conflict: '{new_hist_shortcut}' is already in use by another app. Kept '{old_hist_shortcut}'."
                )
                self.history_shortcut_button.set_shortcut(old_hist_shortcut)
                return
            else:
                self.settings.history_hotkey = new_hist_shortcut
        else:
            self.settings.history_hotkey = new_hist_shortcut

        # Update Settings dataclass
        self.settings.double_tap_enabled = self.double_tap_check.isChecked()
        self.settings.double_tap_interval_ms = self.interval_slider.value()
        self.settings.model = self.model_combo.currentText().strip() or "gemini-3.5-flash"
        self.settings.selection_mode = "rectangle" if self.mode_rect.isChecked() else "freehand"
        self.settings.outside_shape = "keep" if self.shape_keep.isChecked() else "blank"
        self.settings.pinned = self.pinned_check.isChecked()
        self.settings.popup_position = "last_used" if self.pos_last.isChecked() else "near_selection"
        self.settings.launch_at_startup = self.startup_check.isChecked()
        self.settings.save_history = self.save_history_check.isChecked()
        self.settings.save_thumbnails = self.save_thumbnails_check.isChecked()
        if self.settings.save_history:
            self.settings.save_history_prompted = True

        # 1. Save Settings to settings.json
        save_settings(self.settings)

        # 2. Save Key to Windows Credential Manager via Keyring (never in settings.json)
        key_text = self.key_input.text().strip()
        if key_text:
            key_storage.set_api_key(key_text)

        # 3. Configure Windows startup via winreg
        set_launch_at_startup(self.settings.launch_at_startup)

        # 4. Update Double-Tap C Hook live
        if self.double_tap_hook:
            self.double_tap_hook.set_interval(self.settings.double_tap_interval_ms)
            self.double_tap_hook.set_enabled(self.settings.double_tap_enabled)

        # Emit applied signal and close
        self.settings_applied.emit(self.settings)
        self.accept()
