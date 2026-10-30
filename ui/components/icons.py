"""Custom SVG vector icon set for Peachy (20x20 grid, 1.5px stroke).

Rules:
- 1.5 px stroke width
- 20 px viewbox grid
- Zero emoji anywhere
- Clean geometric paths rendered with QSvgRenderer for high-DPI sharpness
"""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# SVG templates on a 20x20 viewBox with stroke="{color}" and stroke-width="1.5"
_SVG_TEMPLATES: Dict[str, str] = {
    # Window controls
    "pin": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6 3h8M10 3v4M5 7h10l-1.5 5H6.5L5 7zM10 12v5"/>
    </svg>""",
    "unpin": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6 3h8M10 3v4M5 7h10l-1.5 5H6.5L5 7zM10 12v5M3 3l14 14"/>
    </svg>""",
    "minimize": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 10h12"/>
    </svg>""",
    "close": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M5 5l10 10M15 5L5 15"/>
    </svg>""",
    # Navigation & actions
    "history": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="10" cy="10" r="7"/>
        <path d="M10 6v4l2.5 2.5"/>
    </svg>""",
    "copy": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="7" y="7" width="9" height="9" rx="2"/>
        <path d="M4 13V5a2 2 0 0 1 2-2h8"/>
    </svg>""",
    "check": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 10.5l4 4 8-8"/>
    </svg>""",
    "crop": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 6V4a1 1 0 0 1 1-1h2M14 3h2a1 1 0 0 1 1 1v2M17 14v2a1 1 0 0 1-1 1h-2M6 17H4a1 1 0 0 1-1-1v-2"/>
    </svg>""",
    "send": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M17 3L2 9l7 2 2 7 6-15zM9 11l8-8"/>
    </svg>""",
    "chevron_down": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6 8l4 4 4-4"/>
    </svg>""",
    "sparkle": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10 2c0 4.5 3.5 8 8 8-4.5 0-8 3.5-8 8 0-4.5-3.5-8-8-8 4.5 0 8-3.5 8-8z"/>
    </svg>""",
    # Preset chips icons
    "solve": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="10" cy="10" r="7"/>
        <circle cx="10" cy="10" r="3"/>
        <path d="M10 1v2M10 17v2M1 10h2M17 10h2"/>
    </svg>""",
    "fix_code": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6 7L3 10l3 3M14 7l3 3-3 3M11 5l-2 10"/>
    </svg>""",
    "translate": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="10" cy="10" r="7"/>
        <path d="M3 10h14M10 3a10 10 0 0 1 3 7 10 10 0 0 1-3 7 10 10 0 0 1-3-7 10 10 0 0 1 3-7z"/>
    </svg>""",
    "summarize": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 6h1.5M8 6h8M4 10h1.5M8 10h8M4 14h1.5M8 14h6"/>
    </svg>""",
    "copy_text": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M5 3h7l4 4v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM12 3v4h4M7 11h6M7 14h4"/>
    </svg>""",
}


def render_svg_string(name: str, color: str = "#A6A1B3") -> str:
    """Return raw SVG XML with specified stroke color."""
    template = _SVG_TEMPLATES.get(name, _SVG_TEMPLATES["sparkle"])
    return template.format(color=color)


def get_svg_pixmap(name: str, color: str = "#A6A1B3", size: int = 20) -> QPixmap:
    """Render SVG vector icon onto a transparent high-DPI QPixmap."""
    svg_data = render_svg_string(name, color).encode("utf-8")
    renderer = QSvgRenderer(QByteArray(svg_data))

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()

    return pixmap


def get_svg_icon(name: str, color: str = "#A6A1B3", size: int = 20) -> QIcon:
    """Return QIcon rendered from vector SVG."""
    pixmap = get_svg_pixmap(name, color, size)
    return QIcon(pixmap)

