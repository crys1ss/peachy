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


def test_crop_freehand_synthetic_mask_blank_and_keep():
    """Verify mask preserves pixels inside shape and blanks pixels outside to white (RGB no alpha)."""
    from capture.geometry import crop_freehand

    width, height = 100, 100
    img = QImage(width, height, QImage.Format.Format_RGB888)

    red = QColor(255, 0, 0)
    green = QColor(0, 255, 0)
    blue = QColor(0, 0, 255)
    yellow = QColor(255, 255, 0)
    white = QColor(255, 255, 255)

    # Fill 4 quadrants: Q1=Red, Q2=Green, Q3=Blue, Q4=Yellow
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

    # Triangle inside Red quadrant: (10, 10) -> (40, 10) -> (10, 40)
    # Bounding box is x: 10..40, y: 10..40 (w=30, h=30)
    triangle_stroke = [(10, 10), (40, 10), (10, 40), (10, 10)]

    # 1. Test "blank" mode (default)
    blank_crop = crop_freehand(img, [triangle_stroke], outside_shape="blank")
    assert blank_crop.width() == 30
    assert blank_crop.height() == 30
    # No alpha channel (pure RGB)
    assert not blank_crop.hasAlphaChannel()
    assert blank_crop.format() == QImage.Format.Format_RGB888

    # Pixel well inside triangle: local (4, 4) -> source (14, 14) -> must be Red
    assert blank_crop.pixelColor(4, 4) == red, "Pixel inside shape must be preserved"

    # Pixel well outside triangle within bbox: local (25, 25) -> source (35, 35) -> must be White
    assert blank_crop.pixelColor(25, 25) == white, "Pixel outside shape must be white"

    # 2. Test "keep" mode
    keep_crop = crop_freehand(img, [triangle_stroke], outside_shape="keep")
    assert keep_crop.width() == 30
    assert keep_crop.height() == 30
    assert not keep_crop.hasAlphaChannel()
    # In keep mode, local (25, 25) comes from source (35, 35) which is Red in source image
    assert keep_crop.pixelColor(4, 4) == red
    assert keep_crop.pixelColor(25, 25) == red, "Keep mode must return plain unblanked box"


def test_crop_freehand_two_strokes_combine_into_one_union_box_and_mask():
    """Verify two separate strokes combine into one union bounding box and composite mask."""
    from capture.geometry import crop_freehand

    width, height = 100, 100
    img = QImage(width, height, QImage.Format.Format_RGB888)

    red = QColor(255, 0, 0)
    green = QColor(0, 255, 0)
    blue = QColor(0, 0, 255)
    yellow = QColor(255, 255, 0)
    white = QColor(255, 255, 255)

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

    # Stroke 1 in Red quadrant: square 10..25, 10..25
    stroke1 = [(10, 10), (25, 10), (25, 25), (10, 25), (10, 10)]
    # Stroke 2 in Yellow quadrant: square 60..75, 60..75
    stroke2 = [(60, 60), (75, 60), (75, 75), (60, 75), (60, 60)]

    # Union bounding box: x: 10..75 (w=65), y: 10..75 (h=65)
    crop = crop_freehand(img, [stroke1, stroke2], outside_shape="blank")
    assert crop.width() == 65
    assert crop.height() == 65
    assert not crop.hasAlphaChannel()

    # Inside Stroke 1 (local 5, 5 -> source 15, 15): Red
    assert crop.pixelColor(5, 5) == red
    # Inside Stroke 2 (local 55, 55 -> source 65, 65): Yellow
    assert crop.pixelColor(55, 55) == yellow
    # Outside both strokes in Green quadrant (local 45, 5 -> source 55, 15): White
    assert crop.pixelColor(45, 5) == white
    # Between both strokes (local 25, 25 -> source 35, 35): White
    assert crop.pixelColor(25, 25) == white

