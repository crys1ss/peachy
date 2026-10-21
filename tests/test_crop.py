"""Synthetic image crop test verifying pixel-for-pixel accuracy."""

import pytest
from PySide6.QtGui import QColor, QImage

from capture.geometry import clamp_crop_box


def create_test_pattern_image(width: int = 100, height: int = 100) -> QImage:
    """Create a 100x100 4-quadrant test image with distinct pure colors:

    - Top-Left: Pure Red (#FF0000)
    - Top-Right: Pure Green (#00FF00)
    - Bottom-Left: Pure Blue (#0000FF)
    - Bottom-Right: Pure Yellow (#FFFF00)
    """
    img = QImage(width, height, QImage.Format_ARGB32)

    red = QColor(255, 0, 0, 255).rgba()
    green = QColor(0, 255, 0, 255).rgba()
    blue = QColor(0, 0, 255, 255).rgba()
    yellow = QColor(255, 255, 0, 255).rgba()

    mid_x = width // 2
    mid_y = height // 2

    for y in range(height):
        for x in range(width):
            if x < mid_x and y < mid_y:
                img.setPixel(x, y, red)
            elif x >= mid_x and y < mid_y:
                img.setPixel(x, y, green)
            elif x < mid_x and y >= mid_y:
                img.setPixel(x, y, blue)
            else:
                img.setPixel(x, y, yellow)

    return img


def test_pixel_for_pixel_quadrant_crops():
    """Verify crops of synthetic quadrants match expected colors pixel-for-pixel."""
    img = create_test_pattern_image(100, 100)

    # 1. Top-Left Crop (Red)
    crop_tl = img.copy(0, 0, 50, 50)
    assert crop_tl.width() == 50
    assert crop_tl.height() == 50
    for y in range(50):
        for x in range(50):
            pixel = crop_tl.pixelColor(x, y)
            assert (pixel.red(), pixel.green(), pixel.blue(), pixel.alpha()) == (255, 0, 0, 255)

    # 2. Top-Right Crop (Green)
    crop_tr = img.copy(50, 0, 50, 50)
    assert crop_tr.width() == 50
    assert crop_tr.height() == 50
    for y in range(50):
        for x in range(50):
            pixel = crop_tr.pixelColor(x, y)
            assert (pixel.red(), pixel.green(), pixel.blue(), pixel.alpha()) == (0, 255, 0, 255)

    # 3. Bottom-Left Crop (Blue)
    crop_bl = img.copy(0, 50, 50, 50)
    assert crop_bl.width() == 50
    assert crop_bl.height() == 50
    for y in range(50):
        for x in range(50):
            pixel = crop_bl.pixelColor(x, y)
            assert (pixel.red(), pixel.green(), pixel.blue(), pixel.alpha()) == (0, 0, 255, 255)

    # 4. Bottom-Right Crop (Yellow)
    crop_br = img.copy(50, 50, 50, 50)
    assert crop_br.width() == 50
    assert crop_br.height() == 50
    for y in range(50):
        for x in range(50):
            pixel = crop_br.pixelColor(x, y)
            assert (pixel.red(), pixel.green(), pixel.blue(), pixel.alpha()) == (255, 255, 0, 255)


def test_clamped_subregion_crop():
    """Verify arbitrary sub-rectangle crop extracts the exact pixel region."""
    img = create_test_pattern_image(100, 100)
    cx, cy, cw, ch = clamp_crop_box(20, 20, 15, 15, img.width(), img.height())

    crop = img.copy(cx, cy, cw, ch)
    assert crop.width() == 15
    assert crop.height() == 15
    # Region (20,20) to (35,35) is entirely inside the Top-Left quadrant (Red)
    for y in range(15):
        for x in range(15):
            pixel = crop.pixelColor(x, y)
            assert (pixel.red(), pixel.green(), pixel.blue()) == (255, 0, 0)
