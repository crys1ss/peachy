"""Pure mathematical geometry functions for screen coordinate transformations and selection.

Completely widget-free and testable across all monitor configurations, DPR scales,
and drag directions.
"""

from __future__ import annotations

from typing import Any, Tuple


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


# ---------------------------------------------------------------------------
# Freehand Selection Pure Geometry Functions
# ---------------------------------------------------------------------------

def add_point_if_far_enough(
    points: list[Tuple[int, int]],
    new_point: Tuple[int, int],
    min_distance: float = 2.0,
) -> bool:
    """Filter incoming stroke points by Euclidean distance in physical pixels.

    Discards points closer than min_distance (default 2.0 px) to the previous point.
    Returns True if the point was added, False if ignored.
    """
    if not points:
        points.append((int(new_point[0]), int(new_point[1])))
        return True

    last_x, last_y = points[-1]
    dx = new_point[0] - last_x
    dy = new_point[1] - last_y
    if (dx * dx + dy * dy) >= (min_distance * min_distance):
        points.append((int(new_point[0]), int(new_point[1])))
        return True
    return False


def close_path(points: list[Tuple[int, int]]) -> list[Tuple[int, int]]:
    """Automatically close a stroke path by connecting the last point to the first point."""
    if not points:
        return []
    if points[0] != points[-1]:
        return list(points) + [points[0]]
    return list(points)


def polygon_bounding_box(points: list[Tuple[int, int]]) -> Tuple[int, int, int, int]:
    """Calculate the (min_x, min_y, w, h) bounding box of a collection of points."""
    if not points:
        return 0, 0, 0, 0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    return min_x, min_y, max(0, max_x - min_x), max(0, max_y - min_y)


def union_bounding_boxes(boxes: list[Tuple[int, int, int, int]]) -> Tuple[int, int, int, int]:
    """Compute the enclosing union of multiple (x, y, w, h) bounding boxes."""
    valid = [b for b in boxes if b[2] > 0 and b[3] > 0]
    if not valid:
        return 0, 0, 0, 0

    min_x = min(b[0] for b in valid)
    min_y = min(b[1] for b in valid)
    max_x = max(b[0] + b[2] for b in valid)
    max_y = max(b[1] + b[3] for b in valid)
    return min_x, min_y, max(0, max_x - min_x), max(0, max_y - min_y)


def polygon_area(points: list[Tuple[int, int]]) -> float:
    """Calculate polygon area using the Shoelace formula."""
    if len(points) < 3:
        return 0.0
    n = len(points)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1] - points[j][0] * points[i][1]
    return abs(area) / 2.0


def is_straight_line(points: list[Tuple[int, int]], tolerance: float = 1.5) -> bool:
    """Check if all points in a stroke lie along a straight line within tolerance."""
    if len(points) < 3:
        return True

    p1 = points[0]
    p2 = points[-1]
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    length_sq = dx * dx + dy * dy

    if length_sq == 0:
        # All points start and end at same point; check distance from p1
        for p in points:
            dist_sq = (p[0] - p1[0]) ** 2 + (p[1] - p1[1]) ** 2
            if dist_sq > tolerance * tolerance:
                return False
        return True

    length = length_sq ** 0.5
    for p in points:
        # Perpendicular distance to line p1 -> p2
        dist = abs(dy * p[0] - dx * p[1] + p2[0] * p1[1] - p2[1] * p1[0]) / length
        if dist > tolerance:
            return False

    return True


def is_degenerate_stroke(
    points: list[Tuple[int, int]],
    min_w: int = 8,
    min_h: int = 8,
    min_area: float = 64.0,
) -> bool:
    """Determine if a freehand stroke is degenerate and should be ignored.

    A stroke is degenerate if:
    - It contains fewer than 3 points
    - Its bounding box width < 8 or height < 8 physical pixels
    - Its enclosed polygon area < 64 square pixels
    - All points lie in a straight line
    """
    if len(points) < 3:
        return True

    _, _, w, h = polygon_bounding_box(points)
    if w < min_w or h < min_h:
        return True

    if polygon_area(points) < min_area:
        return True

    if is_straight_line(points):
        return True

    return False


def _perpendicular_distance(
    pt: Tuple[int, int], line_start: Tuple[int, int], line_end: Tuple[int, int]
) -> float:
    """Perpendicular distance from pt to line segment line_start -> line_end."""
    dx = line_end[0] - line_start[0]
    dy = line_end[1] - line_start[1]
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return ((pt[0] - line_start[0]) ** 2 + (pt[1] - line_start[1]) ** 2) ** 0.5
    return abs(dy * pt[0] - dx * pt[1] + line_end[0] * line_start[1] - line_end[1] * line_start[0]) / (
        length_sq ** 0.5
    )


def _rdp_segment(segment: list[Tuple[int, int]], epsilon: float) -> list[Tuple[int, int]]:
    """Recursive Ramer-Douglas-Peucker reduction on a single segment."""
    if len(segment) <= 2:
        return list(segment)

    start = segment[0]
    end = segment[-1]
    d_max = 0.0
    index = 0

    for i in range(1, len(segment) - 1):
        d = _perpendicular_distance(segment[i], start, end)
        if d > d_max:
            d_max = d
            index = i

    if d_max > epsilon:
        left = _rdp_segment(segment[: index + 1], epsilon)
        right = _rdp_segment(segment[index:], epsilon)
        return left[:-1] + right
    else:
        return [start, end]


def rdp_simplify(points: list[Tuple[int, int]], epsilon: float = 2.0) -> list[Tuple[int, int]]:
    """Simplify polyline using Ramer-Douglas-Peucker while pinning extreme vertices.

    Guarantees that the resulting simplified polygon has the EXACT same bounding box
    (min_x, min_y, max_x, max_y) as the original stroke.
    """
    if len(points) <= 3:
        return list(points)

    # Pin extreme bounding-box indices so RDP simplification cannot change the bbox
    min_x_idx = min(range(len(points)), key=lambda i: (points[i][0], i))
    max_x_idx = max(range(len(points)), key=lambda i: (points[i][0], -i))
    min_y_idx = min(range(len(points)), key=lambda i: (points[i][1], i))
    max_y_idx = max(range(len(points)), key=lambda i: (points[i][1], -i))

    pinned_indices = sorted(set([0, min_x_idx, max_x_idx, min_y_idx, max_y_idx, len(points) - 1]))

    result: list[Tuple[int, int]] = []
    for i in range(len(pinned_indices) - 1):
        sub_start = pinned_indices[i]
        sub_end = pinned_indices[i + 1]
        if sub_start == sub_end:
            continue
        sub_pts = points[sub_start : sub_end + 1]
        simplified_sub = _rdp_segment(sub_pts, epsilon)
        if not result:
            result.extend(simplified_sub)
        else:
            result.extend(simplified_sub[1:])

    return result


def build_polygon_mask(
    strokes: list[list[Tuple[int, int]]],
    bbox: Tuple[int, int, int, int],
    grow_radius: int = 4,
) -> "Image.Image":
    """Build a physical-pixel Pillow grayscale ('L') mask for the given strokes within bbox.

    Grows the mask by grow_radius (using MaxFilter with odd size 2*r + 1) so text
    touching the border line is preserved cleanly.
    """
    from PIL import Image, ImageDraw, ImageFilter

    bx, by, bw, bh = bbox
    if bw <= 0 or bh <= 0:
        return Image.new("L", (1, 1), 0)

    mask = Image.new("L", (bw, bh), 0)
    draw = ImageDraw.Draw(mask)

    for stroke in strokes:
        if len(stroke) < 3:
            continue
        simplified = rdp_simplify(stroke, epsilon=2.0)
        # Translate to local crop coordinates
        local_pts = [(x - bx, y - by) for (x, y) in simplified]
        # Draw filled polygon
        draw.polygon(local_pts, fill=255)
        # Draw 3px outline matching the live stroke
        draw.line(local_pts + [local_pts[0]], fill=255, width=3)

    if grow_radius > 0:
        # Filter size must be odd: 2 * 4 + 1 = 9
        filter_size = 2 * grow_radius + 1
        mask = mask.filter(ImageFilter.MaxFilter(filter_size))

    return mask


def crop_freehand(
    image: Any,
    strokes: list[list[Tuple[int, int]]],
    outside_shape: str = "blank",
) -> Any:
    """Extract freehand selection from image with 'blank' or 'keep' outside pixels.

    Args:
        image: Source QImage of the frozen display.
        strokes: List of closed physical-pixel stroke polygons.
        outside_shape: 'blank' (pixels outside shape become pure white) or 'keep' (plain bbox).

    Returns:
        Cropped QImage in Format_RGB888 (with no alpha channel).
    """
    from PIL import Image
    from PySide6.QtGui import QImage

    if not strokes:
        return QImage()

    boxes = [polygon_bounding_box(s) for s in strokes]
    ux, uy, uw, uh = union_bounding_boxes(boxes)

    cx, cy, cw, ch = clamp_crop_box(ux, uy, uw, uh, image.width(), image.height())
    if cw <= 0 or ch <= 0:
        return QImage()

    if outside_shape == "keep":
        cropped = image.copy(cx, cy, cw, ch)
        return cropped.convertToFormat(QImage.Format.Format_RGB888)

    # outside_shape == 'blank':
    cropped = image.copy(cx, cy, cw, ch).convertToFormat(QImage.Format.Format_RGB888)

    # Convert cropped QImage to PIL RGB Image
    ptr = cropped.bits()
    pil_img = Image.frombuffer("RGB", (cw, ch), ptr, "raw", "RGB", cropped.bytesPerLine(), 1).copy()

    # Build dilated mask
    mask = build_polygon_mask(strokes, (cx, cy, cw, ch), grow_radius=4)

    # Composite with pure white background
    white_bg = Image.new("RGB", (cw, ch), (255, 255, 255))
    composited = Image.composite(pil_img, white_bg, mask)

    # Convert back to QImage Format_RGB888 with no alpha
    data = composited.tobytes("raw", "RGB")
    result = QImage(data, cw, ch, cw * 3, QImage.Format.Format_RGB888).copy()
    return result
