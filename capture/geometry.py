"""Pure mathematical geometry functions for screen coordinate transformations and selection.

Completely widget-free and testable across all monitor configurations, DPR scales,
and drag directions.
"""

from __future__ import annotations

from typing import Tuple


def normalize_rect(x1: int, y1: int, x2: int, y2: int) -> Tuple[int, int, int, int]:
    """Normalize a rectangle defined by two points into canonical (x, y, w, h).

    Supports all 4 drag directions:
    - Top-left to bottom-right
    - Bottom-right to top-left
    - Top-right to bottom-left
    - Bottom-left to top-right

    Returns:
        Tuple of (x, y, width, height) where x, y is the top-left coordinate,
        and width, height >= 0.
    """
    x = min(x1, x2)
    y = min(y1, y2)
    w = abs(x2 - x1)
    h = abs(y2 - y1)
    return x, y, w, h


def clamp_rect(
    x: int,
    y: int,
    w: int,
    h: int,
    bounds_w: int,
    bounds_h: int,
    bounds_x: int = 0,
    bounds_y: int = 0,
) -> Tuple[int, int, int, int]:
    """Clamp a rectangle within boundary dimensions.

    Args:
        x, y, w, h: The rectangle to clamp.
        bounds_w, bounds_h: Width and height of the bounding area.
        bounds_x, bounds_y: Origin of the bounding area (e.g. for negative monitor origins).

    Returns:
        Clamped (x, y, w, h) strictly within the bounds.
    """
    max_x = bounds_x + bounds_w
    max_y = bounds_y + bounds_h

    # Clamp endpoints
    x1 = max(bounds_x, min(x, max_x))
    y1 = max(bounds_y, min(y, max_y))
    x2 = max(bounds_x, min(x + w, max_x))
    y2 = max(bounds_y, min(y + h, max_y))

    clamped_w = max(0, x2 - x1)
    clamped_h = max(0, y2 - y1)
    return x1, y1, clamped_w, clamped_h


def logical_to_physical(
    x: float, y: float, w: float, h: float, dpr: float
) -> Tuple[int, int, int, int]:
    """Convert logical coordinates to physical pixel dimensions based on DPR.

    Args:
        x, y, w, h: Logical rectangle dimensions.
        dpr: Device Pixel Ratio (e.g., 1.0, 1.25, 1.5, 2.0).

    Returns:
        Physical pixel (x, y, w, h) with rounded integer boundaries.
    """
    return (
        round(x * dpr),
        round(y * dpr),
        round(w * dpr),
        round(h * dpr),
    )


def physical_to_logical(
    x: int, y: int, w: int, h: int, dpr: float
) -> Tuple[float, float, float, float]:
    """Convert physical pixel coordinates to logical dimensions based on DPR.

    Args:
        x, y, w, h: Physical pixel rectangle.
        dpr: Device Pixel Ratio.

    Returns:
        Logical (x, y, w, h) float values.
    """
    if dpr <= 0:
        raise ValueError(f"DPR must be positive, got {dpr}")
    return (
        x / dpr,
        y / dpr,
        w / dpr,
        h / dpr,
    )


def clamp_crop_box(
    x: int, y: int, w: int, h: int, img_w: int, img_h: int
) -> Tuple[int, int, int, int]:
    """Ensure a physical crop box does not exceed the image buffer dimensions.

    Args:
        x, y, w, h: Intended physical crop rectangle.
        img_w, img_h: Dimensions of the source image buffer.

    Returns:
        Valid crop rectangle within [0, img_w] x [0, img_h].
    """
    cx = max(0, min(x, img_w))
    cy = max(0, min(y, img_h))
    cw = max(0, min(w, img_w - cx))
    ch = max(0, min(h, img_h - cy))
    return cx, cy, cw, ch


def is_valid_selection(w: int, h: int, min_w: int = 8, min_h: int = 8) -> bool:
    """Return True if selection dimensions meet the minimum required pixel size.

    Selections below 8x8 physical pixels are ignored to prevent accidental clicks.
    """
    return w >= min_w and h >= min_h


def extract_crop(image, crop_box: Tuple[int, int, int, int]):
    """Extract a cropped QImage based on physical coordinates (x, y, w, h).

    Args:
        image: Source QImage or QPixmap.
        crop_box: Physical pixel rectangle (x, y, w, h).

    Returns:
        Cropped QImage/QPixmap clamped within source dimensions.
    """
    x, y, w, h = crop_box
    cx, cy, cw, ch = clamp_crop_box(x, y, w, h, image.width(), image.height())
    if cw <= 0 or ch <= 0:
        return type(image)()
    return image.copy(cx, cy, cw, ch)


def clamp_popup_to_screen(
    x: int, y: int, w: int, h: int, screen_x: int, screen_y: int, screen_w: int, screen_h: int
) -> Tuple[int, int]:
    """Pure mathematical function to clamp a popup window completely within screen boundaries.

    Ensures top-left (x, y) keeps the entire window (w x h) visible within the screen
    work area [screen_x, screen_x + screen_w] x [screen_y, screen_y + screen_h].
    Handles multiple monitors and negative coordinate offsets.
    """
    max_x = screen_x + screen_w - w
    max_y = screen_y + screen_h - h

    clamped_x = max(screen_x, min(x, max_x)) if max_x >= screen_x else screen_x
    clamped_y = max(screen_y, min(y, max_y)) if max_y >= screen_y else screen_y

    return clamped_x, clamped_y
