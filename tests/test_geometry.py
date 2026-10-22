"""Unit tests for capture/geometry.py math functions."""

import pytest

from capture.geometry import (
    add_point_if_far_enough,
    clamp_crop_box,
    clamp_rect,
    close_path,
    is_degenerate_stroke,
    is_straight_line,
    is_valid_selection,
    logical_to_physical,
    normalize_rect,
    physical_to_logical,
    polygon_area,
    polygon_bounding_box,
    rdp_simplify,
    union_bounding_boxes,
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


def test_add_point_if_far_enough_filtering():
    """Verify points closer than 2.0 px Euclidean distance are ignored."""
    pts: list[tuple[int, int]] = []
    # First point always added
    assert add_point_if_far_enough(pts, (10, 10), min_distance=2.0) is True
    assert pts == [(10, 10)]

    # Point 1 px away (dx=1, dy=0, dist=1 < 2) -> ignored
    assert add_point_if_far_enough(pts, (11, 10), min_distance=2.0) is False
    assert len(pts) == 1

    # Point diagonal 1 px away (dx=1, dy=1, dist=1.414 < 2) -> ignored
    assert add_point_if_far_enough(pts, (11, 11), min_distance=2.0) is False
    assert len(pts) == 1

    # Point 2 px away (dx=2, dy=0, dist=2.0 >= 2) -> added
    assert add_point_if_far_enough(pts, (12, 10), min_distance=2.0) is True
    assert pts == [(10, 10), (12, 10)]

    # Point diagonal (dx=2, dy=2, dist=2.828 >= 2) -> added
    assert add_point_if_far_enough(pts, (14, 12), min_distance=2.0) is True
    assert len(pts) == 3


def test_close_path():
    """Verify open paths are closed by appending the start point."""
    open_path = [(10, 10), (50, 10), (50, 50)]
    closed = close_path(open_path)
    assert closed == [(10, 10), (50, 10), (50, 50), (10, 10)]

    # Already closed path is left unchanged
    already_closed = [(10, 10), (50, 10), (50, 50), (10, 10)]
    assert close_path(already_closed) == already_closed
    assert close_path([]) == []


def test_polygon_bounding_box_directions_and_negative_origins():
    """Verify polygon bounding box across all draw directions and negative screen coordinates."""
    # Clockwise stroke
    cw = [(10, 20), (60, 20), (60, 90), (10, 90)]
    assert polygon_bounding_box(cw) == (10, 20, 50, 70)

    # Counter-clockwise stroke
    ccw = [(10, 90), (60, 90), (60, 20), (10, 20)]
    assert polygon_bounding_box(ccw) == (10, 20, 50, 70)

    # Irregular loop
    loop = [(25, 30), (70, 15), (95, 60), (50, 110), (15, 80)]
    assert polygon_bounding_box(loop) == (15, 15, 80, 95)

    # Monitor with negative origins (e.g. x=-1920, y=-56)
    neg_stroke = [(-1500, -30), (-1300, -30), (-1300, 40), (-1500, 40)]
    assert polygon_bounding_box(neg_stroke) == (-1500, -30, 200, 70)

    assert polygon_bounding_box([]) == (0, 0, 0, 0)


def test_polygon_bounding_box_across_dprs():
    """Verify physical pixel bounding box across DPR 1.0, 1.25, 1.5, 2.0."""
    logical_pts = [(10, 20), (50, 20), (50, 60), (10, 60)]  # 40x40 logical
    dprs = [1.0, 1.25, 1.5, 2.0]
    expected_wh = [(40, 40), (50, 50), (60, 60), (80, 80)]

    for dpr, (exp_w, exp_h) in zip(dprs, expected_wh):
        phys_pts = [(round(x * dpr), round(y * dpr)) for x, y in logical_pts]
        _, _, w, h = polygon_bounding_box(phys_pts)
        assert (w, h) == (exp_w, exp_h)


def test_polygon_area_shoelace():
    """Verify Shoelace formula polygon area calculation."""
    # Right-angled triangle (base 10, height 10, area 50)
    triangle = [(0, 0), (10, 0), (0, 10)]
    assert polygon_area(triangle) == 50.0

    # Square 20x20, area 400
    square = [(0, 0), (20, 0), (20, 20), (0, 20)]
    assert polygon_area(square) == 400.0

    # Single point or line has 0 area
    assert polygon_area([(0, 0)]) == 0.0
    assert polygon_area([(0, 0), (10, 10)]) == 0.0


def test_is_straight_line():
    """Verify collinear or near-collinear points are identified as straight lines."""
    # Perfectly horizontal line
    horiz = [(0, 10), (5, 10), (10, 10), (20, 10)]
    assert is_straight_line(horiz) is True

    # Perfectly diagonal line
    diag = [(0, 0), (5, 5), (10, 10), (25, 25)]
    assert is_straight_line(diag) is True

    # Curved triangle
    triangle = [(0, 0), (20, 30), (40, 0)]
    assert is_straight_line(triangle) is False


def test_degenerate_strokes_rejected():
    """Verify single clicks, straight lines, tiny boxes, and tiny areas are rejected."""
    # 1 point (single click)
    assert is_degenerate_stroke([(10, 10)]) is True

    # 2 points (straight line segment)
    assert is_degenerate_stroke([(10, 10), (20, 20)]) is True

    # Collinear straight line of multiple points
    assert is_degenerate_stroke([(0, 0), (10, 10), (20, 20), (30, 30)]) is True

    # Tiny bounding box < 8x8 (e.g. 6x6 square)
    tiny_box = [(0, 0), (6, 0), (6, 6), (0, 6)]
    assert is_degenerate_stroke(tiny_box) is True

    # Tiny area < 64 sq px (e.g. 5x10 rectangle = 50 sq px)
    tiny_area = [(0, 0), (5, 0), (5, 10), (0, 10)]
    assert is_degenerate_stroke(tiny_area) is True

    # Valid loop: 20x20 square (w=20 >= 8, h=20 >= 8, area=400 >= 64, not straight)
    valid_loop = [(10, 10), (30, 10), (30, 30), (10, 30)]
    assert is_degenerate_stroke(valid_loop) is False


def test_rdp_simplify_preserves_bounding_box_and_reduces_points():
    """Verify Ramer-Douglas-Peucker reduces point count while strictly keeping bounding box."""
    # Create a noisy polygon with 60 points along a 100x100 square
    points: list[tuple[int, int]] = []
    # Top edge with jitter
    for x in range(0, 101, 5):
        points.append((x, 0 if x in (0, 100) else (1 if x % 2 == 0 else 0)))
    # Right edge with jitter
    for y in range(5, 101, 5):
        points.append((100 if y in (0, 100) else (99 if y % 2 == 0 else 100), y))
    # Bottom edge with jitter
    for x in range(95, -1, -5):
        points.append((x, 100 if x in (0, 100) else (99 if x % 2 == 0 else 100)))
    # Left edge with jitter
    for y in range(95, 0, -5):
        points.append((0 if y in (0, 100) else (1 if y % 2 == 0 else 0), y))

    orig_bbox = polygon_bounding_box(points)
    assert orig_bbox == (0, 0, 100, 100)
    assert len(points) > 50

    simplified = rdp_simplify(points, epsilon=2.0)

    # 1. Point count is significantly reduced
    assert len(simplified) < len(points)
    assert len(simplified) <= 15

    # 2. Bounding box is guaranteed 100% identical!
    simp_bbox = polygon_bounding_box(simplified)
    assert simp_bbox == orig_bbox


def test_union_bounding_boxes():
    """Verify union of multiple bounding boxes."""
    b1 = (10, 20, 30, 40)   # x: 10..40, y: 20..60
    b2 = (50, 30, 20, 50)   # x: 50..70, y: 30..80
    b3 = (0, 0, 0, 0)       # Invalid, ignored

    union = union_bounding_boxes([b1, b2, b3])
    # Min x: 10, min y: 20, max x: 70, max y: 80 -> w: 60, h: 60
    assert union == (10, 20, 60, 60)
    assert union_bounding_boxes([]) == (0, 0, 0, 0)
