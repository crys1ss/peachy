"""Custom SVG vector icon set for Peachy (20x20 grid, 1.5px stroke).

Rules (docs/REDESIGN.md Section 3.3):
- 1.5 px stroke width
- 20 px viewbox grid
- Clean geometric paths rendered with QSvgRenderer for high-DPI sharpness
- Dynamic runtime recolouring via string format substitution
- Zero emoji in chrome
"""

from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# SVG templates on a 20x20 viewBox with stroke="{color}" and stroke-width="1.5"
_SVG_TEMPLATES: Dict[str, str] = {
    # Core window & chrome controls
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
    "x": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M5 5l10 10M15 5L5 15"/>
    </svg>""",
    "check": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M4 10.5l4 4 8-8"/>
    </svg>""",

    # Navigation & chrome
    "plus": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10 4v12M4 10h12"/>
    </svg>""",
    "search": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="9" cy="9" r="5.5"/>
        <path d="M13 13l4 4"/>
    </svg>""",
    "sidebar": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="14" height="14" rx="2"/>
        <path d="M8 3v14"/>
    </svg>""",
    "more": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="5" cy="10" r="1.2" fill="{color}" stroke="{color}"/>
        <circle cx="10" cy="10" r="1.2" fill="{color}" stroke="{color}"/>
        <circle cx="15" cy="10" r="1.2" fill="{color}" stroke="{color}"/>
    </svg>""",
    "edit": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M13.5 3.5l3 3L6.5 16.5 3 17l.5-3.5 10-10z"/>
    </svg>""",
    "regenerate": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3.5 10a6.5 6.5 0 0 1 11.2-4.4L17 7M17 3v4h-4M16.5 10a6.5 6.5 0 0 1-11.2 4.4L3 13M3 17v-4h4"/>
    </svg>""",
    "paperclip": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14.5 9.5l-5.5 5.5a3.5 3.5 0 0 1-5-5l6.5-6.5a2.5 2.5 0 0 1 3.5 3.5l-6 6a1.5 1.5 0 0 1-2.1-2.1l5.5-5.5"/>
    </svg>""",
    "image": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="14" height="14" rx="2"/>
        <circle cx="7.5" cy="7.5" r="1.5"/>
        <path d="M17 13l-4-4-7 8"/>
    </svg>""",
    "scissors": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="6" cy="6" r="2.5"/>
        <circle cx="6" cy="14" r="2.5"/>
        <path d="M8 7.5L16 14M8 12.5L16 6"/>
    </svg>""",
    "send": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M17 3L2 9l7 2 2 7 6-15zM9 11l8-8"/>
    </svg>""",
    "stop": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="5" y="5" width="10" height="10" rx="2"/>
    </svg>""",
    "settings": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="10" cy="10" r="3"/>
        <path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M4.7 15.3l1.4-1.4M13.9 6.1l1.4-1.4"/>
    </svg>""",
    "chevron": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M7 6l4 4-4 4"/>
    </svg>""",
    "chevron_down": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6 8l4 4 4-4"/>
    </svg>""",
    "chevron_up": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M6 12l4-4 4 4"/>
    </svg>""",
    "sun": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="10" cy="10" r="4"/>
        <path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.3 4.3l1.4 1.4M14.3 14.3l1.4 1.4M4.3 15.7l1.4-1.4M14.3 5.7l1.4-1.4"/>
    </svg>""",
    "moon": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M15.5 11.5A6.5 6.5 0 1 1 8.5 4.5a5.5 5.5 0 0 0 7 7z"/>
    </svg>""",
    "keyboard": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="5" width="14" height="10" rx="2"/>
        <path d="M6 8h.01M9 8h.01M12 8h.01M15 8h.01M6 11h8"/>
    </svg>""",
    "shield": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10 3s5 1.5 7 2.5v5c0 4.5-3.5 7-7 8.5-3.5-1.5-7-4-7-8.5v-5C5 4.5 10 3 10 3z"/>
    </svg>""",
    "info": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="10" cy="10" r="7"/>
        <path d="M10 9v5M10 6.5h.01"/>
    </svg>""",

    # Legacy & specific utility actions
    "history": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="10" cy="10" r="7"/>
        <path d="M10 6v4l2.5 2.5"/>
    </svg>""",
    "copy": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="7" y="7" width="9" height="9" rx="2"/>
        <path d="M4 13V5a2 2 0 0 1 2-2h8"/>
    </svg>""",
    "crop": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 6V4a1 1 0 0 1 1-1h2M14 3h2a1 1 0 0 1 1 1v2M17 14v2a1 1 0 0 1-1 1h-2M6 17H4a1 1 0 0 1-1-1v-2"/>
    </svg>""",
    "sparkle": """<svg viewBox="0 0 20 20" fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M10 2c0 4.5 3.5 8 8 8-4.5 0-8 3.5-8 8 0-4.5-3.5-8-8-8 4.5 0 8-3.5 8-8z"/>
    </svg>""",
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


def get_available_icon_names() -> list[str]:
    """Return sorted list of all available icon identifier strings."""
    return sorted(_SVG_TEMPLATES.keys())


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
