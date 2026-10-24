"""Diagnostic script verifying freehand selection masking and cropping.

Creates a synthetic image with coloured squares, applies a hardcoded triangle stroke,
builds the dilated mask composited over pure white, saves the result PNG to a temp folder,
and prints the resulting size and pixel colours inside and outside the shape.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QColor, QImage
from capture.geometry import crop_freehand, polygon_bounding_box


def main() -> int:
    print("============================================================")
    print("Peachy: Freehand Selection Diagnostic Check")
    print("============================================================")

    # 1. Create synthetic 100x100 RGB image with 4 coloured quadrants
    width, height = 100, 100
    img = QImage(width, height, QImage.Format.Format_RGB888)

    red = QColor(255, 0, 0)
    green = QColor(0, 255, 0)
    blue = QColor(0, 0, 255)
    yellow = QColor(255, 255, 0)

    for y in range(height):
        for x in range(width):
            if x < 50 and y < 50:
                img.setPixelColor(x, y, red)
            elif x >= 50 and y < 50:
                img.setPixelColor(x, y, green)
            elif x < 50 and y >= 50:
                img.setPixelColor(x, y, blue)
            else:
                img.setPixelColor(x, y, yellow)

    print(f"Created synthetic image: {width}x{height} px with 4 coloured quadrants.")
    print("  Quadrant 1 (Top-Left):     Red   RGB(255, 0, 0)")
    print("  Quadrant 2 (Top-Right):    Green RGB(0, 255, 0)")
    print("  Quadrant 3 (Bottom-Left):  Blue  RGB(0, 0, 255)")
    print("  Quadrant 4 (Bottom-Right): Yellow RGB(255, 255, 0)")

    # 2. Hard-coded triangle stroke located in the Red quadrant (10, 10) to (40, 40)
    # Bounding box is (10, 10, 30, 30)
    triangle_stroke = [(10, 10), (40, 10), (10, 40), (10, 10)]
    bx, by, bw, bh = polygon_bounding_box(triangle_stroke)
    print(f"\nHardcoded triangle stroke: {triangle_stroke}")
    print(f"Stroke bounding box: origin=({bx}, {by}), size={bw}x{bh} physical px")

    # 3. Crop with outside_shape='blank' (default: pixels outside shape become pure white)
    blank_result = crop_freehand(img, [triangle_stroke], outside_shape="blank")

    # 4. Save result PNG to temp folder
    temp_dir = Path(tempfile.gettempdir()) / "peachy_freehand_check"
    temp_dir.mkdir(parents=True, exist_ok=True)
    out_path = temp_dir / "freehand_triangle_blank.png"
    blank_result.save(str(out_path), "PNG")

    print(f"\nResult saved to: {out_path}")
    print(f"Result image dimensions: {blank_result.width()} x {blank_result.height()} px")
    print(f"Result format: {blank_result.format().name} (has alpha: {blank_result.hasAlphaChannel()})")

    # 5. Check pixel colours inside vs outside shape
    # Inside triangle: local (4, 4) corresponds to source (14, 14) which is Red
    inside_color = blank_result.pixelColor(4, 4)
    # Outside triangle within bbox: local (25, 25) corresponds to source (35, 35) which is blanked to White
    outside_color = blank_result.pixelColor(25, 25)

    print(f"\nPixel Inspection:")
    print(f"  Inside triangle  at local (4, 4):   RGB({inside_color.red()}, {inside_color.green()}, {inside_color.blue()})")
    print(f"  Outside triangle at local (25, 25): RGB({outside_color.red()}, {outside_color.green()}, {outside_color.blue()})")

    # Verify correctness
    assert blank_result.width() == 30 and blank_result.height() == 30, "Bounding box size mismatch!"
    assert (inside_color.red(), inside_color.green(), inside_color.blue()) == (255, 0, 0), "Inside pixel not preserved!"
    assert (outside_color.red(), outside_color.green(), outside_color.blue()) == (255, 255, 255), "Outside pixel not blanked to white!"
    assert not blank_result.hasAlphaChannel(), "PNG must have no alpha channel!"

    # 6. Also check outside_shape='keep' mode
    keep_result = crop_freehand(img, [triangle_stroke], outside_shape="keep")
    keep_inside = keep_result.pixelColor(4, 4)
    keep_outside = keep_result.pixelColor(25, 25)
    print(f"\n'keep' mode verification:")
    print(f"  Inside  at (4, 4):   RGB({keep_inside.red()}, {keep_inside.green()}, {keep_inside.blue()})")
    print(f"  Outside at (25, 25): RGB({keep_outside.red()}, {keep_outside.green()}, {keep_outside.blue()})")

    assert (keep_outside.red(), keep_outside.green(), keep_outside.blue()) == (255, 0, 0), "Keep mode should preserve bounding box unchanged"

    print("\nFREEHAND CHECK PASSED SUCCESSFULLY!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
