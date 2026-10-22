"""Generate multi-resolution peachy.ico from resources/sparkle.svg."""

from __future__ import annotations

import io
from pathlib import Path
import sys

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


def generate_ico() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    svg_path = Path("resources/sparkle.svg")
    if not svg_path.exists():
        raise FileNotFoundError(f"SVG mascot not found at {svg_path}")

    renderer = QSvgRenderer(str(svg_path))
    sizes = [16, 32, 48, 256]
    pil_images = []

    for s in sizes:
        qimg = QImage(s, s, QImage.Format.Format_ARGB32)
        qimg.fill(Qt.GlobalColor.transparent)
        painter = QPainter(qimg)
        renderer.render(painter)
        painter.end()

        # Convert QImage via PNG buffer to PIL Image for color accuracy
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        qimg.save(buf, "PNG")
        pil_img = Image.open(io.BytesIO(bytes(ba.data())))
        pil_images.append(pil_img)

    out_ico = Path("resources/peachy.ico")
    out_ico.parent.mkdir(parents=True, exist_ok=True)

    # Save multi-size ICO: largest first
    pil_images[-1].save(
        str(out_ico),
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=pil_images[:-1],
    )
    print(f"Generated {out_ico} containing resolutions: {sizes}")


if __name__ == "__main__":
    generate_ico()
