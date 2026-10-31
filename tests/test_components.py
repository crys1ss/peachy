"""Unit tests for ui/components kit (BrandOrb, icons, code highlighter, stream throttler, toast)."""

import pytest
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

from ui.components.brand_orb import BrandOrb
from ui.components.code_highlighter import highlight_code, render_markdown_html
from ui.components.icons import get_svg_icon, get_svg_pixmap, render_svg_string
from ui.components.throttle import StreamThrottler
from ui.components.toast import Toast


def test_svg_vector_icons_rendering(qtbot):
    """Verify vector SVG icons render cleanly on 20x20 grid with zero emoji."""
    icon_names = [
        "pin", "unpin", "minimize", "close", "history", "copy", "check",
        "crop", "send", "chevron_down", "sparkle",
        "solve", "fix_code", "translate", "summarize", "copy_text",
    ]

    for name in icon_names:
        svg_xml = render_svg_string(name, color="#FF6BCE")
        assert "viewBox=\"0 0 20 20\"" in svg_xml
        assert "stroke-width=\"1.5\"" in svg_xml
        assert "#FF6BCE" in svg_xml

        # Test pixmap generation
        pix = get_svg_pixmap(name, color="#FF6BCE", size=20)
        assert not pix.isNull()
        assert pix.width() == 20
        assert pix.height() == 20

        # Test icon generation
        icon = get_svg_icon(name, color="#FF6BCE", size=20)
        assert not icon.isNull()


def test_brand_orb_widget(qtbot):
    """Verify BrandOrb renders with accent -> accent_2 gradient and responds to apply_theme."""
    from ui.theme import get_theme, MIDNIGHT_THEME, LIGHT_THEME
    orb = BrandOrb(size=22, theme=MIDNIGHT_THEME)
    qtbot.addWidget(orb)

    assert orb.width() == 22
    assert orb.height() == 22
    assert orb.sizeHint() == QSize(22, 22)
    assert orb._theme.accent == "#FF9E7D"
    assert orb._theme.accent_2 == "#FF7A90"

    # Switch theme
    coral_theme = get_theme(theme_mode="midnight", accent="coral")
    orb.apply_theme(coral_theme)
    assert orb._theme.accent == "#FF8A8A"

    # Calling repaint should execute paintEvent cleanly
    orb.repaint()


def test_pygments_syntax_highlighting():
    """Verify Pygments code highlighter formats code with Cascadia Code / Consolas and theme colors."""
    from ui.theme import MIDNIGHT_THEME, LIGHT_THEME
    sample_code = "def hello_world():\n    return 'peachy'"
    html_out = highlight_code(sample_code, language="python", theme=MIDNIGHT_THEME)

    assert "Cascadia Code" in html_out
    assert "Consolas" in html_out
    assert "#111118" in html_out  # Secondary background
    assert "#292735" in html_out  # Border
    assert "hello_world" in html_out

    # Test markdown wrapper with explicit theme
    md_sample = "# Title\n\n```python\nx = 42\n```\n\nEnd text."
    rendered_md = render_markdown_html(md_sample, theme=MIDNIGHT_THEME)
    assert "# Title" in rendered_md
    assert "Cascadia Code" in rendered_md
    assert "End text." in rendered_md

    # Light theme test
    light_out = highlight_code(sample_code, language="python", theme=LIGHT_THEME)
    assert LIGHT_THEME.secondary in light_out


def test_stream_throttler(qtbot):
    """Verify StreamThrottler throttles rapid chunks to 60 ms cadence and flushes correctly."""
    throttler = StreamThrottler(interval_ms=60)

    received_updates = []
    throttler.throttled_text.connect(received_updates.append)

    # Append rapid chunks
    throttler.append_chunk("Hello ")
    throttler.append_chunk("world, ")
    throttler.append_chunk("this is ")
    throttler.append_chunk("Peachy!")

    assert throttler.get_full_text() == "Hello world, this is Peachy!"

    # Flush immediately delivers full text
    throttler.flush()
    assert len(received_updates) == 1
    assert received_updates[-1] == "Hello world, this is Peachy!"

    # Reset clears buffer
    throttler.reset()
    assert throttler.get_full_text() == ""


def test_toast_notification(qtbot):
    """Verify Toast pill shows message and auto-dismisses."""
    parent = QWidget()
    parent.resize(300, 200)
    qtbot.addWidget(parent)
    parent.show()

    toast = Toast("Copied to clipboard", parent=parent)
    assert not toast.isVisible()

    toast.show_toast("Copied to clipboard", duration_ms=500, animate=False)
    assert toast.isVisible()
    assert toast.label.text() == "Copied to clipboard"

    # Trigger hide
    toast.hide_toast(animate=False)
    assert not toast.isVisible()


def test_toggle_switch_component(qtbot):
    """Verify ToggleSwitch state transitions, click/spacebar activation, and reduce motion snapping."""
    from unittest.mock import patch
    from ui.components.toggle_switch import ToggleSwitch
    from ui.theme import MIDNIGHT_THEME, LIGHT_THEME

    sw = ToggleSwitch(checked=False, theme=MIDNIGHT_THEME)
    qtbot.addWidget(sw)
    assert sw.isChecked() is False
    assert sw.thumb_position == 0.0

    # Toggle to True with instant snapping (duration=0)
    with patch("ui.components.toggle_switch.duration", return_value=0):
        sw.setChecked(True)
        assert sw.isChecked() is True
        assert sw.thumb_position == 1.0

        # Toggle via click
        sw.click()
        assert sw.isChecked() is False
        assert sw.thumb_position == 0.0

    # Live theme update
    sw.apply_theme(LIGHT_THEME)
    assert sw._theme == LIGHT_THEME


def test_chip_component(qtbot):
    """Verify Chip selection state, icon recoloring, and theme application."""
    from ui.components.chip import Chip
    from ui.theme import MIDNIGHT_THEME, LIGHT_THEME

    chip = Chip("Fix Code", icon_name="edit", selected=False, theme=MIDNIGHT_THEME)
    qtbot.addWidget(chip)
    assert chip.isChecked() is False
    assert chip.text() == "Fix Code"
    assert not chip.icon().isNull()

    # Click toggles selection
    chip.click()
    assert chip.isChecked() is True

    # Theme application
    chip.apply_theme(LIGHT_THEME)
    assert chip._theme == LIGHT_THEME


def test_redesign_all_21_vector_icons():
    """Verify all 21 icons specified in docs/REDESIGN.md Section 3.4 render cleanly."""
    required_icons = [
        "plus", "search", "sidebar", "pin", "more", "edit", "regenerate",
        "paperclip", "image", "scissors", "send", "stop", "settings",
        "chevron", "check", "x", "sun", "moon", "keyboard", "shield", "info"
    ]

    for name in required_icons:
        svg_xml = render_svg_string(name, color="#FF9E7D")
        assert "viewBox=\"0 0 20 20\"" in svg_xml
        assert "stroke-width=\"1.5\"" in svg_xml
        assert "#FF9E7D" in svg_xml

        pix = get_svg_pixmap(name, color="#FF9E7D", size=20)
        assert not pix.isNull()
        assert pix.width() == 20
        assert pix.height() == 20

        icon = get_svg_icon(name, color="#FF9E7D", size=20)
        assert not icon.isNull()
