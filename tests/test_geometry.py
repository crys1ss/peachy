"""Unit tests for capture/geometry.py."""

import pytest

from capture.geometry import (
    clamp_crop_box,
    clamp_rect,
    is_valid_selection,
    logical_to_physical,
    normalize_rect,
    physical_to_logical,
)


def test_normalize_rect_all_four_drag_directions():
    """Verify rect normalization produces identical (x, y, w, h) for all 4 drag directions."""
    # 1. Top-Left to Bottom-Right
    r1 = normalize_rect(10.0, 20.0, 100.0, 150.0)
    assert r1 == (10.0, 20.0, 90.0, 130.0)

    # 2. Bottom-Right to Top-Left
    r2 = normalize_rect(100.0, 150.0, 10.0, 20.0)
    assert r2 == (10.0, 20.0, 90.0, 130.0)

    # 3. Top-Right to Bottom-Left
    r3 = normalize_rect(100.0, 20.0, 10.0, 150.0)
    assert r3 == (10.0, 20.0, 90.0, 130.0)

    # 4. Bottom-Left to Top-Right
    r4 = normalize_rect(10.0, 150.0, 100.0, 20.0)
    assert r4 == (10.0, 20.0, 90.0, 130.0)


def test_clamp_rect_within_bounds():
    """Rect inside bounds remains unchanged."""
    clamped = clamp_rect(50.0, 50.0, 100.0, 80.0, 0.0, 0.0, 1920.0, 1080.0)
    assert clamped == (50.0, 50.0, 100.0, 80.0)


def test_clamp_rect_exceeding_right_and_bottom():
    """Rect extending past the right or bottom edges is clamped to the boundary."""
    clamped = clamp_rect(1900.0, 1000.0, 50.0, 100.0, 0.0, 0.0, 1920.0, 1080.0)
    assert clamped == (1900.0, 1000.0, 20.0, 80.0)


def test_clamp_rect_exceeding_left_and_top():
    """Rect dragging past 0 is clamped at 0."""
    clamped = clamp_rect(-30.0, -20.0, 100.0, 100.0, 0.0, 0.0, 1920.0, 1080.0)
    assert clamped == (0.0, 0.0, 70.0, 80.0)


def test_clamp_rect_negative_monitor_origins():
    """Test clamping with secondary monitors with negative coordinates (e.g. left or above primary)."""
    # Monitor at x=-1920, y=-56, width=1536, height=864
    bounds = (-1920.0, -56.0, 1536.0, 864.0)

    # Valid rect inside negative monitor
    c1 = clamp_rect(-1500.0, 0.0, 200.0, 200.0, *bounds)
    assert c1 == (-1500.0, 0.0, 200.0, 200.0)

    # Rect extending past left edge of negative monitor
    c2 = clamp_rect(-2000.0, -56.0, 150.0, 100.0, *bounds)
    assert c2 == (-1920.0, -56.0, 70.0, 100.0)


@pytest.mark.parametrize(
    "dpr, logical, expected_physical",
    [
        (1.0, (100, 100, 200, 150), (100, 100, 200, 150)),
        (1.25, (100, 100, 200, 150), (125, 125, 250, 188)),
        (1.5, (100, 100, 200, 150), (150, 150, 300, 225)),
        (2.0, (100, 100, 200, 150), (200, 200, 400, 300)),
    ],
)
def test_logical_to_physical_various_dpr(dpr, logical, expected_physical):
    """Test logical to physical pixel coordinate scaling across standard Windows DPRs."""
    res = logical_to_physical(*logical, dpr)
    assert res == expected_physical


def test_physical_to_logical_round_trip():
    """Test round-trip conversion between physical and logical."""
    dpr = 1.25
    phys = (125, 125, 250, 188)
    lx, ly, lw, lh = physical_to_logical(*phys, dpr)
    assert (lx, ly, lw) == (100.0, 100.0, 200.0)
    assert round(lh, 1) == 150.4


@pytest.mark.parametrize(
    "w, h, expected",
    [
        (7, 7, False),
        (7, 8, False),
        (8, 7, False),
        (3, 3, False),
        (0, 0, False),
        (-5, -5, False),
        (8, 8, True),
        (9, 8, True),
        (8, 9, True),
        (1920, 1080, True),
    ],
)
def test_is_valid_selection_threshold(w, h, expected):
    """Selections under 8x8 physical pixels must be rejected."""
    assert is_valid_selection(w, h, min_size=8) is expected


def test_clamp_crop_box_image_limits():
    """Crop box strictly bounded by image dimensions."""
    box = clamp_crop_box(1900, 1050, 100, 100, 1920, 1080)
    assert box == (1900, 1050, 20, 30)

    box_neg = clamp_crop_box(-50, -50, 100, 100, 1920, 1080)
    assert box_neg == (0, 0, 50, 50)
