"""Peachy Midnight Component Gallery.

Interactive showcase displaying every Peachy design system component across
Midnight and Light modes with all 4 accent options (Peach, Coral, Rose, Lavender).
Runs completely offline with zero API key dependencies.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ui.components.brand_orb import BrandOrb
from ui.components.chip import Chip
from ui.components.code_highlighter import render_markdown_html
from ui.components.icons import get_available_icon_names, get_svg_icon
from ui.components.toast import Toast
from ui.components.toggle_switch import ToggleSwitch
from config.settings import Settings
from tests.fakes.fake_chat_session import FakeChatSession
from ui.main_window import MainWindow
from ui.theme import (
    ThemeTokens,
    get_app_font,
    get_code_font,
    get_theme,
    set_font_scale,
)


class ComponentGalleryWindow(QWidget):
    """Component gallery showcasing all Midnight Peachy UI widgets and accents."""

    def __init__(self, theme_mode: str = "midnight", accent: str = "peach", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._mode = theme_mode
        self._accent = accent
        self._font_scale = 100
        self.theme: ThemeTokens = get_theme(theme_mode=self._mode, accent=self._accent)

        self.setWindowTitle("Peachy - Midnight Design System Gallery")
        self.resize(960, 840)
        self.setMinimumSize(800, 600)

        self._build_ui()
        self._apply_theme()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Top Control Toolbar
        self.toolbar = QFrame(self)
        self.toolbar.setFixedHeight(56)
        tb_layout = QHBoxLayout(self.toolbar)
        tb_layout.setContentsMargins(16, 8, 16, 8)
        tb_layout.setSpacing(16)

        # Mode Selector
        tb_layout.addWidget(QLabel("Theme:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Midnight", "midnight")
        self.mode_combo.addItem("Light", "light")
        self.mode_combo.setCurrentIndex(0 if self._mode == "midnight" else 1)
        self.mode_combo.currentIndexChanged.connect(self._on_theme_changed)
        tb_layout.addWidget(self.mode_combo)

        # Accent Selector
        tb_layout.addWidget(QLabel("Accent:"))
        self.accent_combo = QComboBox()
        self.accent_combo.addItem("Peach (#FF9E7D)", "peach")
        self.accent_combo.addItem("Coral (#FF8A8A)", "coral")
        self.accent_combo.addItem("Rose (#FF7AB6)", "rose")
        self.accent_combo.addItem("Lavender (#B9A4FF)", "lavender")
        idx = ["peach", "coral", "rose", "lavender"].index(self._accent)
        self.accent_combo.setCurrentIndex(idx)
        self.accent_combo.currentIndexChanged.connect(self._on_theme_changed)
        tb_layout.addWidget(self.accent_combo)

        # Font Scale
        tb_layout.addWidget(QLabel("Scale:"))
        self.scale_combo = QComboBox()
        self.scale_combo.addItem("90%", 90)
        self.scale_combo.addItem("100%", 100)
        self.scale_combo.addItem("110%", 110)
        self.scale_combo.addItem("125%", 125)
        self.scale_combo.setCurrentIndex(1)
        self.scale_combo.currentIndexChanged.connect(self._on_scale_changed)
        tb_layout.addWidget(self.scale_combo)

        tb_layout.addStretch()

        self.toast_btn = QPushButton("Show Sample Toast")
        self.toast_btn.clicked.connect(lambda: self.toast.show_toast("Copied to clipboard"))
        tb_layout.addWidget(self.toast_btn)

        root_layout.addWidget(self.toolbar)

        # Scrollable gallery canvas
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.canvas = QWidget()
        self.canvas_layout = QVBoxLayout(self.canvas)
        self.canvas_layout.setContentsMargins(32, 24, 32, 32)
        self.canvas_layout.setSpacing(28)

        self._populate_sections()

        scroll.setWidget(self.canvas)
        root_layout.addWidget(scroll, stretch=1)

        # Toast host
        self.toast = Toast(parent=self)

    def _create_section(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("sectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        header = QLabel(title)
        header.setFont(get_app_font(15, bold=True))
        header.setObjectName("sectionTitle")
        layout.addWidget(header)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setObjectName("hairlineDivider")
        layout.addWidget(div)

        self.canvas_layout.addWidget(card)
        return card, layout

    def _populate_sections(self) -> None:
        # 1. Brand & Mascot
        _, brand_layout = self._create_section("1. Brand Orb & Breathing Halo")
        b_row = QHBoxLayout()
        b_row.setSpacing(24)

        orb_col1 = QVBoxLayout()
        orb_col1.addWidget(QLabel("Static Brand Mark (22 px)"))
        self.orb_small = BrandOrb(size=22)
        orb_col1.addWidget(self.orb_small, alignment=Qt.AlignmentFlag.AlignLeft)
        b_row.addLayout(orb_col1)

        orb_col2 = QVBoxLayout()
        orb_col2.addWidget(QLabel("Hero Brand Mark (48 px)"))
        self.orb_large = BrandOrb(size=48)
        orb_col2.addWidget(self.orb_large, alignment=Qt.AlignmentFlag.AlignLeft)
        b_row.addLayout(orb_col2)

        orb_col3 = QVBoxLayout()
        orb_col3.addWidget(QLabel("Wordmark & Greeting"))
        self.title_lbl = QLabel("peachy")
        self.title_lbl.setFont(get_app_font(26, bold=True))
        self.sub_lbl = QLabel("Good evening, Zidane")
        self.sub_lbl.setFont(get_app_font(14))
        orb_col3.addWidget(self.title_lbl)
        orb_col3.addWidget(self.sub_lbl)
        b_row.addLayout(orb_col3)

        b_row.addStretch()
        brand_layout.addLayout(b_row)

        # 2. Toggle Switches
        _, switch_layout = self._create_section("2. Animated Pill Toggle Switches")
        sw_row = QHBoxLayout()
        sw_row.setSpacing(32)

        self.sw_active = ToggleSwitch(checked=True, theme=self.theme)
        lbl_sw1 = QLabel("Active (Checked)")
        sw_row.addWidget(self.sw_active)
        sw_row.addWidget(lbl_sw1)

        self.sw_inactive = ToggleSwitch(checked=False, theme=self.theme)
        lbl_sw2 = QLabel("Inactive (Unchecked)")
        sw_row.addWidget(self.sw_inactive)
        sw_row.addWidget(lbl_sw2)

        self.sw_disabled = ToggleSwitch(checked=True, theme=self.theme)
        self.sw_disabled.setEnabled(False)
        lbl_sw3 = QLabel("Disabled")
        sw_row.addWidget(self.sw_disabled)
        sw_row.addWidget(lbl_sw3)

        sw_row.addStretch()
        switch_layout.addLayout(sw_row)

        # 3. Selectable Chips
        _, chip_layout = self._create_section("3. Selectable Chips (8 px Radius)")
        ch_row = QHBoxLayout()
        ch_row.setSpacing(12)

        self.chip1 = Chip("Short", selected=True, theme=self.theme)
        self.chip2 = Chip("Detailed", selected=False, theme=self.theme)
        self.chip3 = Chip("Explain a screenshot", icon_name="crop", selected=False, theme=self.theme)
        self.chip4 = Chip("Debug code", icon_name="fix_code", selected=True, theme=self.theme)
        self.chip5 = Chip("Disabled", icon_name="info", selected=False, theme=self.theme)
        self.chip5.setEnabled(False)

        ch_row.addWidget(self.chip1)
        ch_row.addWidget(self.chip2)
        ch_row.addWidget(self.chip3)
        ch_row.addWidget(self.chip4)
        ch_row.addWidget(self.chip5)
        ch_row.addStretch()
        chip_layout.addLayout(ch_row)

        # 4. Buttons & Controls
        _, btn_layout = self._create_section("4. Buttons & Interactive States")
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_primary = QPushButton("Primary Action")
        self.btn_primary.setObjectName("primaryButton")
        self.btn_primary.setFont(get_app_font(13, bold=True))

        self.btn_secondary = QPushButton("Secondary")
        self.btn_secondary.setObjectName("secondaryButton")
        self.btn_secondary.setFont(get_app_font(12))

        self.btn_icon1 = QPushButton()
        self.btn_icon1.setObjectName("iconButton")
        self.btn_icon1.setIcon(get_svg_icon("search", color=self.theme.text_secondary, size=16))

        self.btn_icon2 = QPushButton()
        self.btn_icon2.setObjectName("iconButton")
        self.btn_icon2.setIcon(get_svg_icon("settings", color=self.theme.text_secondary, size=16))

        btn_row.addWidget(self.btn_primary)
        btn_row.addWidget(self.btn_secondary)
        btn_row.addWidget(self.btn_icon1)
        btn_row.addWidget(self.btn_icon2)
        btn_row.addStretch()
        btn_layout.addLayout(btn_row)

        # 5. Inputs & Fields
        _, input_layout = self._create_section("5. Composer Inputs & Focus Glow")
        in_row = QHBoxLayout()
        in_row.setSpacing(12)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask anything, or snip your screen...")
        self.input_field.setFont(get_app_font(13))
        self.input_field.setFixedHeight(40)
        in_row.addWidget(self.input_field)

        self.send_mock_btn = QPushButton()
        self.send_mock_btn.setObjectName("primaryButton")
        self.send_mock_btn.setFixedSize(36, 36)
        self.send_mock_btn.setIcon(get_svg_icon("send", color=self.theme.accent_ink, size=16))
        in_row.addWidget(self.send_mock_btn)

        input_layout.addLayout(in_row)

        # 6. Vector Icons Grid (1.5 px Stroke)
        _, icon_section_layout = self._create_section("6. Vector SVG Icons (1.5 px Stroke, Dynamic Recolouring)")
        icon_grid = QGridLayout()
        icon_grid.setSpacing(10)

        names = get_available_icon_names()
        for idx, name in enumerate(names):
            row = idx // 7
            col = idx % 7
            cell = QFrame()
            cell.setObjectName("iconCell")
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(6, 6, 6, 6)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            ico_lbl = QLabel()
            ico_lbl.setPixmap(get_svg_icon(name, color=self.theme.accent, size=20).pixmap(20, 20))
            ico_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            name_lbl = QLabel(name)
            name_lbl.setFont(get_app_font(10))
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_lbl.setObjectName("iconCellLabel")

            cell_layout.addWidget(ico_lbl)
            cell_layout.addWidget(name_lbl)
            icon_grid.addWidget(cell, row, col)

        icon_section_layout.addLayout(icon_grid)

        # 7. Monospace Code & Pygments Highlighting
        _, code_layout = self._create_section("7. Code Highlighting (Cascadia Code / Consolas)")
        self.code_browser = QTextBrowser()
        self.code_browser.setFixedHeight(140)
        self.code_browser.setObjectName("codeBrowser")

        code_snippet = """```python
def ask_peachy(query: str, fast: bool = True) -> str:
    # Midnight Peachy instant response
    return f"Peachy ready: {query}"
```"""
        self.code_browser.setHtml(render_markdown_html(code_snippet, theme=self.theme))
        code_layout.addWidget(self.code_browser)

        # 8. Main Window Shell Preview
        _, main_layout = self._create_section("8. Main Window Shell (Fake Data Preview)")
        main_desc = QLabel("MainWindow preview with Sidebar, WelcomeView, and FakeChatSession:")
        main_layout.addWidget(main_desc)

        self._fake_store = _create_mock_store()
        self._fake_settings = Settings(display_name="Zidane", theme=self._mode, accent=self._accent)
        self._fake_session = FakeChatSession()

        self.preview_main_win = MainWindow(
            store=self._fake_store,
            settings=self._fake_settings,
            chat_session=self._fake_session,
            parent=self.canvas,
        )
        self.preview_main_win.setFixedHeight(540)
        main_layout.addWidget(self.preview_main_win)

    def _on_theme_changed(self) -> None:
        self._mode = self.mode_combo.currentData()
        self._accent = self.accent_combo.currentData()
        self.theme = get_theme(theme_mode=self._mode, accent=self._accent)
        self._apply_theme()

    def _on_scale_changed(self) -> None:
        self._font_scale = self.scale_combo.currentData()
        set_font_scale(self._font_scale)
        self._apply_theme()

    def set_gallery_state(self, mode: str, accent: str, scale: int = 100) -> None:
        """Programmatically switch gallery to a specific theme, accent, and scale."""
        self._mode = mode
        self._accent = accent
        self._font_scale = scale
        set_font_scale(self._font_scale)
        self.theme = get_theme(theme_mode=mode, accent=accent)

        self.mode_combo.setCurrentIndex(0 if mode == "midnight" else 1)
        acc_idx = ["peach", "coral", "rose", "lavender"].index(accent)
        self.accent_combo.setCurrentIndex(acc_idx)
        self._apply_theme()

    def _apply_theme(self) -> None:
        t = self.theme
        self.setStyleSheet(f"""
            QMainWindow, QScrollArea, QFrame#galleryCanvas {{
                background-color: {t.background};
                color: {t.text};
                font-family: 'Inter', 'Segoe UI Variable Text', sans-serif;
            }}
            QLabel {{
                background-color: transparent;
                background: transparent;
                color: {t.text};
                font-family: 'Inter', 'Segoe UI Variable Text', sans-serif;
            }}
            QFrame#sectionCard {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 14px;
            }}
            QLabel#sectionTitle {{
                color: {t.accent};
                font-size: 15px;
                font-weight: 600;
            }}
            QFrame#hairlineDivider {{
                background-color: {t.hairline};
                border: none;
            }}
            QFrame#iconCell {{
                background-color: {t.secondary};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            QLabel#iconCellLabel {{
                color: {t.text_secondary};
                font-size: 10px;
            }}
            QLineEdit {{
                background-color: {t.secondary};
                color: {t.text};
                border: 1px solid {t.border};
                border-radius: 10px;
                padding: 8px 12px;
            }}
            QLineEdit:focus {{
                border: 1.5px solid {t.accent};
            }}
            QPushButton#primaryButton {{
                background-color: {t.accent};
                color: {t.accent_ink};
                border-radius: 10px;
                padding: 8px 16px;
                font-weight: 600;
                border: none;
            }}
            QPushButton#primaryButton:hover {{
                background-color: {t.accent_2};
            }}
            QPushButton#secondaryButton {{
                background-color: {t.surface};
                color: {t.text};
                border: 1px solid {t.border};
                border-radius: 10px;
                padding: 8px 16px;
                font-weight: 500;
            }}
            QPushButton#secondaryButton:hover {{
                background-color: {t.hover};
                border-color: {t.accent};
                color: {t.accent};
            }}
            QPushButton#iconButton {{
                background-color: transparent;
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 6px;
            }}
            QPushButton#iconButton:hover {{
                background-color: {t.hover};
                border-color: {t.accent};
            }}
            QComboBox {{
                background-color: {t.secondary};
                color: {t.text};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 4px 8px;
            }}
            QTextBrowser#codeBrowser {{
                background-color: {t.secondary};
                border: 1px solid {t.border};
                border-radius: 10px;
            }}
        """)

        # Update child components
        if hasattr(self, "sw_active"):
            self.sw_active.apply_theme(t)
            self.sw_inactive.apply_theme(t)
            self.sw_disabled.apply_theme(t)
            self.chip1.apply_theme(t)
            self.chip2.apply_theme(t)
            self.chip3.apply_theme(t)
            self.chip4.apply_theme(t)
            self.chip5.apply_theme(t)
            self.toast.theme = t
            self.title_lbl.setStyleSheet(f"color: {t.accent};")
            self.sub_lbl.setStyleSheet(f"color: {t.text_secondary};")

            code_snippet = """```python
def ask_peachy(query: str, fast: bool = True) -> str:
    # Midnight Peachy instant response
    return f"Peachy ready: {query}"
```"""
            self.code_browser.setHtml(render_markdown_html(code_snippet, theme=t))

        if hasattr(self, "preview_main_win"):
            self.preview_main_win.apply_theme(t.name, t.accent)


def _create_mock_store():
    class MockStore:
        def __init__(self):
            self._convs = [
                {"id": 1, "title": "PySide6 Custom Delegates", "preview": "How do I paint a 2 px gradient marker in Qt?", "created_at": "2026-10-31 10:15:00", "pinned": True},
                {"id": 2, "title": "SQLite WAL Recovery", "preview": "Handling locked companion files gracefully...", "created_at": "2026-10-31 08:30:00", "pinned": False},
                {"id": 3, "title": "Midnight Design System", "preview": "Deep charcoal background tokens and WCAG 4.5:1 ratios.", "created_at": "2026-10-30 18:20:00", "pinned": False},
            ]
            self._messages = {
                1: [
                    {"id": 1, "role": "user", "text": "How do I paint a 2 px gradient marker in Qt?"},
                    {"id": 2, "role": "model", "text": "Use `QLinearGradient` inside your `QStyledItemDelegate.paint` method!"},
                ]
            }
        def list_conversations(self):
            return list(self._convs)
        def get_conversation(self, cid):
            for c in self._convs:
                if c["id"] == cid:
                    return c
            return None
        def get_messages(self, cid):
            return list(self._messages.get(cid, []))
        def rename_conversation(self, cid, title):
            for c in self._convs:
                if c["id"] == cid:
                    c["title"] = title
        def set_pinned(self, cid, pinned):
            for c in self._convs:
                if c["id"] == cid:
                    c["pinned"] = pinned
        def delete_conversation(self, cid):
            self._convs = [c for c in self._convs if c["id"] != cid]
    return MockStore()


def capture_main_window_screenshots(out_dir: Path) -> list[Path]:
    """Capture main_welcome.png, main_sidebar.png, and main_collapsed.png in out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []

    store = _create_mock_store()
    settings = Settings(display_name="Zidane", theme="midnight", accent="peach", save_history_prompted=False)
    session = FakeChatSession()

    win = MainWindow(store=store, settings=settings, chat_session=session)
    win.resize(1100, 720)
    win.show()
    QApplication.processEvents()

    # 1. Welcome view
    p1 = out_dir / "main_welcome.png"
    win.grab().save(str(p1), "PNG")
    saved.append(p1)

    # 2. Main with active conversation loaded (sidebar visible)
    win.sidebar._is_collapsed = False
    win.sidebar.setFixedWidth(win.sidebar.EXPANDED_WIDTH)
    win.sidebar._update_collapsed_layout()
    win.load_conversation(1)
    QApplication.processEvents()
    p2 = out_dir / "main_sidebar.png"
    win.grab().save(str(p2), "PNG")
    saved.append(p2)

    # 3. Main with collapsed sidebar
    win.sidebar._is_collapsed = True
    win.sidebar.setFixedWidth(win.sidebar.COLLAPSED_WIDTH)
    win.sidebar._update_collapsed_layout()
    QApplication.processEvents()
    p3 = out_dir / "main_collapsed.png"
    win.grab().save(str(p3), "PNG")
    saved.append(p3)

    win.close()
    return saved


def capture_gallery_screenshots(out_dir: Path) -> list[Path]:
    """Capture screenshots for Midnight and Light across all 4 accents."""
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = []

    win = ComponentGalleryWindow(theme_mode="midnight", accent="peach")
    win.show()
    QApplication.processEvents()

    modes = ["midnight", "light"]
    accents = ["peach", "coral", "rose", "lavender"]

    for m in modes:
        for a in accents:
            win.set_gallery_state(mode=m, accent=a)
            QApplication.processEvents()
            # Capture pixmap
            pixmap = win.grab()
            filename = f"gallery_{m}_{a}.png"
            file_path = out_dir / filename
            pixmap.save(str(file_path), "PNG")
            saved_paths.append(file_path)

    win.close()
    return saved_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Peachy Component Gallery")
    parser.add_argument("--save-screenshots", action="store_true", help="Capture gallery screenshots and exit")
    parser.add_argument("--out-dir", type=str, default="docs/screens/gallery", help="Screenshot output directory")
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)

    if args.save_screenshots:
        out = REPO_ROOT / args.out_dir
        saved = capture_gallery_screenshots(out)
        print(f"Captured {len(saved)} gallery screenshots in {out}")

        midnight_dir = REPO_ROOT / "docs/screens/midnight"
        mw_saved = capture_main_window_screenshots(midnight_dir)
        print(f"Captured {len(mw_saved)} main window screenshots in {midnight_dir}")
        return 0

    win = ComponentGalleryWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
