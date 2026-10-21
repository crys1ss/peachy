"""Test pixel-for-pixel exact cropping using synthetic images."""

from PySide6.QtGui import QColor, QImage

from capture.geometry import extract_crop


def test_crop_synthetic_colored_squares():
    """Verify that cropping a synthetic grid of colors extracts exact pixel values."""
    width, height = 100, 100
    img = QImage(width, height, QImage.Format.Format_ARGB32)

    red = QColor(255, 0, 0, 255)
    green = QColor(0, 255, 0, 255)
    blue = QColor(0, 0, 255, 255)
    yellow = QColor(255, 255, 0, 255)

    # Fill 4 quadrants of 50x50
    # Q1 (top-left): Red
    # Q2 (top-right): Green
    # Q3 (bottom-left): Blue
    # Q4 (bottom-right): Yellow
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

    # 1. Crop Top-Right (Green quadrant)
    green_crop = extract_crop(img, (50, 0, 50, 50))
    assert green_crop.width() == 50
    assert green_crop.height() == 50
    for y in range(50):
        for x in range(50):
            assert green_crop.pixelColor(x, y) == green, f"Mismatch at ({x}, {y})"

    # 2. Crop Bottom-Left (Blue quadrant)
    blue_crop = extract_crop(img, (0, 50, 50, 50))
    assert blue_crop.width() == 50
    assert blue_crop.height() == 50
    for y in range(50):
        for x in range(50):
            assert blue_crop.pixelColor(x, y) == blue, f"Mismatch at ({x}, {y})"

    # 3. Crop Center 50x50 spanning all 4 quadrants (x: 25..75, y: 25..75)
    center_crop = extract_crop(img, (25, 25, 50, 50))
    assert center_crop.width() == 50
    assert center_crop.height() == 50

    # Inside center_crop:
    # (0..24, 0..24) corresponds to source (25..49, 25..49) -> Red
    # (25..49, 0..24) corresponds to source (50..74, 25..49) -> Green
    # (0..24, 25..49) corresponds to source (25..49, 50..74) -> Blue
    # (25..49, 25..49) corresponds to source (50..74, 50..74) -> Yellow
    for y in range(50):
        for x in range(50):
            if x < 25 and y < 25:
                assert center_crop.pixelColor(x, y) == red
            elif x >= 25 and y < 25:
                assert center_crop.pixelColor(x, y) == green
            elif x < 25 and y >= 25:
                assert center_crop.pixelColor(x, y) == blue
            else:
                assert center_crop.pixelColor(x, y) == yellow


def test_crop_out_of_bounds_clamping():
    """Verify that crop box extending beyond image edges is safely clamped."""
    img = QImage(100, 100, QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 255, 255))

    crop = extract_crop(img, (80, 80, 50, 50))
    assert crop.width() == 20
    assert crop.height() == 20
