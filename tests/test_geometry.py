"""Unit tests for capture/geometry.py math functions."""

import pytest

from capture.geometry import (
    clamp_crop_box,
    clamp_rect,
    is_valid_selection,
    logical_to_physical,
    normalize_rect,
    physical_to_logical,
)


def test_normalize_rect_all_four_directions():
    """Verify that dragging in all 4 cardinal directions produces positive, identical boxes."""
    # Top-left to bottom-right
    assert normalize_rect(10, 20, 110, 220) == (10, 20, 100, 200)

    # Bottom-right to top-left
    assert normalize_rect(110, 220, 10, 20) == (10, 20, 100, 200)

    # Top-right to bottom-left
    assert normalize_rect(110, 20, 10, 220) == (10, 20, 100, 200)

    # Bottom-left to top-right
    assert normalize_rect(10, 220, 110, 20) == (10, 20, 100, 200)


def test_normalize_rect_zero_size():
    """Verify single-click (zero width/height) normalization."""
    assert normalize_rect(50, 50, 50, 50) == (50, 50, 0, 0)


def test_clamp_rect_within_bounds():
    """Verify rect fully inside bounds is unchanged."""
    assert clamp_rect(10, 10, 50, 50, 1920, 1080) == (10, 10, 50, 50)


def test_clamp_rect_exceeding_right_bottom():
    """Verify rect dragging outside right/bottom boundary is clamped."""
    assert clamp_rect(1900, 1060, 50, 50, 1920, 1080) == (1900, 1060, 20, 20)


def test_clamp_rect_negative_origin():
    """Verify rect on a monitor with negative origins (e.g. left of primary)."""
    # Monitor at x=-1920, y=-56 with w=1536, h=864
    # Selection within bounds:
    assert clamp_rect(-1800, 0, 100, 100, 1536, 864, bounds_x=-1920, bounds_y=-56) == (
        -1800,
        0,
        100,
        100,
    )

    # Drag exceeding left border (e.g. x=-2000):
    assert clamp_rect(-2000, 0, 200, 100, 1536, 864, bounds_x=-1920, bounds_y=-56) == (
        -1920,
        0,
        120,
        100,
    )


def test_logical_to_physical_various_dprs():
    """Verify logical to physical pixel conversion across standard DPRs."""
    # 100% scaling (DPR 1.0)
    assert logical_to_physical(10, 20, 100, 200, 1.0) == (10, 20, 100, 200)

    # 125% scaling (DPR 1.25)
    # 10 * 1.25 = 12.5 -> 12, 100 * 1.25 = 125, 200 * 1.25 = 250
    assert logical_to_physical(10, 20, 100, 200, 1.25) == (12, 25, 125, 250)

    # 150% scaling (DPR 1.5)
    assert logical_to_physical(10, 20, 100, 200, 1.5) == (15, 30, 150, 300)

    # 200% scaling (DPR 2.0)
    assert logical_to_physical(10, 20, 100, 200, 2.0) == (20, 40, 200, 400)


def test_physical_to_logical_roundtrip():
    """Verify physical to logical conversion."""
    lx, ly, lw, lh = physical_to_logical(15, 30, 150, 300, 1.5)
    assert (lx, ly, lw, lh) == (10.0, 20.0, 100.0, 200.0)

    with pytest.raises(ValueError):
        physical_to_logical(10, 10, 10, 10, 0.0)


def test_clamp_crop_box():
    """Verify crop box clamping within physical image dimensions."""
    # Within bounds
    assert clamp_crop_box(10, 10, 100, 100, 1920, 1080) == (10, 10, 100, 100)

    # Exceeding edge
    assert clamp_crop_box(1900, 1050, 50, 50, 1920, 1080) == (1900, 1050, 20, 30)

    # Negative coordinates clamped to 0
    assert clamp_crop_box(-10, -20, 50, 50, 1920, 1080) == (0, 0, 50, 50)


def test_is_valid_selection_threshold():
    """Verify selections < 8x8 physical pixels are rejected."""
    assert is_valid_selection(8, 8) is True
    assert is_valid_selection(100, 50) is True
    assert is_valid_selection(7, 8) is False
    assert is_valid_selection(8, 7) is False
    assert is_valid_selection(3, 3) is False
    assert is_valid_selection(0, 0) is False
