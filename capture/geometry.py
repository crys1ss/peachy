"""Pure geometry math functions for Peachy screen capture and overlay.

Contains zero GUI widget dependencies so all functions can be unit-tested cleanly:
- Rect normalization across all four drag directions
- Multi-monitor boundary clamping
- Logical-to-physical coordinate transformations with device pixel ratios (DPR)
- Selection validation and crop box calculations
"""

from __future__ import annotations

from typing import Tuple


def normalize_rect(
    start_x: float,
    start_y: float,
    current_x: float,
    current_y: float,
) -> Tuple[float, float, float, float]:
    """Normalize two arbitrary points from any drag direction into (x, y, width, height).

    Handles all 4 drag directions:
    - Top-Left to Bottom-Right
    - Bottom-Right to Top-Left
    - Top-Right to Bottom-Left
    - Bottom-Left to Top-Right
    """
    x = min(start_x, current_x)
    y = min(start_y, current_y)
    width = abs(current_x - start_x)
    height = abs(current_y - start_y)
    return x, y, width, height


def clamp_rect(
    x: float,
    y: float,
    w: float,
    h: float,
    bounds_x: float,
    bounds_y: float,
    bounds_w: float,
    bounds_h: float,
) -> Tuple[float, float, float, float]:
    """Clamp a rectangle to remain strictly within the specified bounding rectangle."""
    # Ensure non-negative bounds width/height
    bounds_right = bounds_x + max(0.0, bounds_w)
    bounds_bottom = bounds_y + max(0.0, bounds_h)

    # Clamp left/top
    clamped_left = max(bounds_x, min(x, bounds_right))
    clamped_top = max(bounds_y, min(y, bounds_bottom))

    # Clamp right/bottom
    orig_right = x + max(0.0, w)
    orig_bottom = y + max(0.0, h)

    clamped_right = max(clamped_left, min(orig_right, bounds_right))
    clamped_bottom = max(clamped_top, min(orig_bottom, bounds_bottom))

    clamped_w = clamped_right - clamped_left
    clamped_h = clamped_bottom - clamped_top

    return clamped_left, clamped_top, clamped_w, clamped_h


def logical_to_physical(
    x: float,
    y: float,
    w: float,
    h: float,
    dpr: float,
) -> Tuple[int, int, int, int]:
    """Convert logical coordinates and dimensions to physical device pixels."""
    if dpr <= 0.0:
        dpr = 1.0
    return (
        int(round(x * dpr)),
        int(round(y * dpr)),
        int(round(w * dpr)),
        int(round(h * dpr)),
    )


def physical_to_logical(
    x: int,
    y: int,
    w: int,
    h: int,
    dpr: float,
) -> Tuple[float, float, float, float]:
    """Convert physical device pixels to logical coordinates."""
    if dpr <= 0.0:
        dpr = 1.0
    return (
        x / dpr,
        y / dpr,
        w / dpr,
        h / dpr,
    )


def is_valid_selection(phys_w: int, phys_h: int, min_size: int = 8) -> bool:
    """Validate that the selected physical crop meets the minimum dimensions (default 8x8)."""
    return phys_w >= min_size and phys_h >= min_size


def clamp_crop_box(
    crop_x: int,
    crop_y: int,
    crop_w: int,
    crop_h: int,
    img_width: int,
    img_height: int,
) -> Tuple[int, int, int, int]:
    """Clamp a pixel crop rectangle strictly within image buffer bounds."""
    x1 = max(0, min(crop_x, img_width))
    y1 = max(0, min(crop_y, img_height))
    x2 = max(x1, min(crop_x + crop_w, img_width))
    y2 = max(y1, min(crop_y + crop_h, img_height))
    return x1, y1, x2 - x1, y2 - y1
