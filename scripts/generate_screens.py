"""Render synthetic screenshot artifacts of each Peachy view using QWidget.grab().

Saves pixel-perfect previews to docs/screens/ using fake/mock data:
- docs/screens/ask_view.png
- docs/screens/thinking_view.png
- docs/screens/answer_view.png
- docs/screens/error_view.png
- docs/screens/minimized_pill.png

Usage:
    python scripts/generate_screens.py
"""

from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

# Ensure repository root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ui.peachy_popup import PeachyPopup


def create_mock_thumbnail(w: int = 240, h: int = 110) -> QPixmap:
    """Create cute synthetic thumbnail diagram for AskView."""
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("#1E1A1D"))

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Grid lines
    painter.setPen(QColor("#352A33"))
    for x in range(0, w, 24):
        painter.drawLine(x, 0, x, h)
    for y in range(0, h, 24):
        painter.drawLine(0, y, w, y)

    # Sample code-like lines
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#F472B6"))
    painter.drawRoundedRect(16, 20, 60, 8, 4, 4)

    painter.setBrush(QColor("#9E98A0"))
    painter.drawRoundedRect(84, 20, 110, 8, 4, 4)

    painter.setBrush(QColor("#F5F0F3"))
    painter.drawRoundedRect(32, 40, 140, 8, 4, 4)
    painter.drawRoundedRect(32, 58, 90, 8, 4, 4)

    painter.setBrush(QColor("#EC4899"))
    painter.drawRoundedRect(16, 78, 50, 8, 4, 4)

    painter.end()
    return QPixmap.fromImage(img)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)

    out_dir = PROJECT_ROOT / "docs" / "screens"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Generating Peachy Day 4 synthetic view previews in docs/screens/...")

    popup = PeachyPopup(pinned=True, answer_length="short")
    popup.resize(380, 360)

    # 1. Ask View
    mock_thumb = create_mock_thumbnail()
    popup.show_ask(mock_thumb)
    popup.ask_view.input_field.setText("What does this function return?")
    app.processEvents()
    pix_ask = popup.grab()
    ask_path = out_dir / "ask_view.png"
    pix_ask.save(str(ask_path), "PNG")
    print(f"  • Saved: {ask_path}")

    # 2. Thinking View
    popup.show_thinking()
    app.processEvents()
    pix_thinking = popup.grab()
    thinking_path = out_dir / "thinking_view.png"
    pix_thinking.save(str(thinking_path), "PNG")
    print(f"  • Saved: {thinking_path}")

    # 3. Answer View
    sample_markdown = (
        "The function calculates the **Euclidean distance** between two points.\n\n"
        "```python\n"
        "def distance(p1, p2):\n"
        "    return math.hypot(p2.x - p1.x, p2.y - p1.y)\n"
        "```\n\n"
        "Key takeaway: It returns a `float` representing straight-line length."
    )
    popup.show_answer(sample_markdown, question="What does this function return?", is_first_answer=True)
    app.processEvents()
    pix_answer = popup.grab()
    answer_path = out_dir / "answer_view.png"
    pix_answer.save(str(answer_path), "PNG")
    print(f"  • Saved: {answer_path}")

    # 4. Error View
    popup.show_error("Gemini rate limit exceeded. Please wait a moment and try again.")
    app.processEvents()
    pix_error = popup.grab()
    error_path = out_dir / "error_view.png"
    pix_error.save(str(error_path), "PNG")
    print(f"  • Saved: {error_path}")

    # 5. Minimized Pill
    popup.hide()
    popup.pill.show()
    app.processEvents()
    pix_pill = popup.pill.grab()
    pill_path = out_dir / "minimized_pill.png"
    pix_pill.save(str(pill_path), "PNG")
    print(f"  • Saved: {pill_path}")

    popup.pill.hide()
    popup.close()

    print("All view preview screenshots successfully generated!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
