"""
Geometric helper functions for violation detection.

Provides IoU computation, bounding-box manipulation, centroid extraction,
proximity checks, and line-crossing tests used throughout the violation
detection modules.
"""

from __future__ import annotations

import math
from typing import Sequence

# Type aliases for clarity
BBox = tuple[float, float, float, float]  # (x1, y1, x2, y2)
Point = tuple[float, float]               # (x, y)


def bbox_area(bbox: BBox) -> float:
    """Return the area of an axis-aligned bounding box.

    Parameters
    ----------
    bbox:
        ``(x1, y1, x2, y2)`` with ``x2 >= x1`` and ``y2 >= y1``.
    """
    x1, y1, x2, y2 = bbox
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def bbox_intersection_area(a: BBox, b: BBox) -> float:
    """Compute the intersection area between two bounding boxes."""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def iou(a: BBox, b: BBox) -> float:
    """Compute Intersection-over-Union between two bounding boxes.

    Returns
    -------
    float
        IoU value in ``[0, 1]``.
    """
    inter = bbox_intersection_area(a, b)
    area_a = bbox_area(a)
    area_b = bbox_area(b)
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def bbox_centroid(bbox: BBox) -> Point:
    """Return the centre point ``(cx, cy)`` of a bounding box."""
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def bbox_bottom_center(bbox: BBox) -> Point:
    """Return the bottom-centre ``(cx, y2)`` of a bounding box."""
    x1, _y1, x2, y2 = bbox
    return ((x1 + x2) / 2.0, y2)


def euclidean_distance(a: Point, b: Point) -> float:
    """Euclidean distance between two 2-D points."""
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def bbox_contains(outer: BBox, inner: BBox, tolerance: float = 0.0) -> bool:
    """Check if *outer* bbox fully contains *inner* bbox (with tolerance).

    A positive *tolerance* relaxes the containment check by expanding
    the outer box by that many pixels on each side.
    """
    return (
        inner[0] >= outer[0] - tolerance
        and inner[1] >= outer[1] - tolerance
        and inner[2] <= outer[2] + tolerance
        and inner[3] <= outer[3] + tolerance
    )


def bbox_overlap_ratio(a: BBox, b: BBox) -> float:
    """Fraction of *a*'s area overlapping with *b*.

    Returns
    -------
    float
        ``intersection_area / area(a)`` in ``[0, 1]``.
    """
    inter = bbox_intersection_area(a, b)
    area_a = bbox_area(a)
    if area_a <= 0.0:
        return 0.0
    return inter / area_a


def upper_portion(bbox: BBox, fraction: float = 0.35) -> BBox:
    """Return the upper *fraction* of a bounding box.

    Useful for isolating the head region of a rider detection.

    Parameters
    ----------
    fraction:
        Proportion of height from the top, e.g. 0.35 → top 35%.
    """
    x1, y1, x2, y2 = bbox
    height = y2 - y1
    return (x1, y1, x2, y1 + height * fraction)


def point_crosses_line(
    point_prev: Point,
    point_curr: Point,
    line_y: float,
) -> bool:
    """Check if a point has crossed a horizontal line between two frames.

    The crossing is detected when the y-coordinates of consecutive
    positions straddle *line_y* (from above to below or vice-versa).
    """
    return (point_prev[1] <= line_y < point_curr[1]) or (
        point_curr[1] <= line_y < point_prev[1]
    )


def point_crosses_segment(
    point_prev: Point,
    point_curr: Point,
    seg_start: Point,
    seg_end: Point,
) -> bool:
    """Detect if a moving point has crossed an arbitrary line segment.

    Uses a cross-product sign test to determine whether the trajectory
    ``point_prev → point_curr`` intersects the segment
    ``seg_start → seg_end``.
    """

    def _cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    d1 = _cross(seg_start, seg_end, point_prev)
    d2 = _cross(seg_start, seg_end, point_curr)
    d3 = _cross(point_prev, point_curr, seg_start)
    d4 = _cross(point_prev, point_curr, seg_end)

    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    ):
        return True
    return False


def compute_direction_degrees(trajectory: Sequence[Point]) -> float | None:
    """Estimate the dominant direction of travel from a trajectory.

    Uses a weighted average of bearing angles between consecutive
    positions, with later segments receiving higher weight.

    Returns
    -------
    float or None
        Direction in degrees ``[0, 360)`` where 0 = right / east,
        90 = down / south (image coords).  ``None`` if the trajectory
        has fewer than 2 points or total displacement is negligible.
    """
    if len(trajectory) < 2:
        return None

    total_weight = 0.0
    weighted_sin = 0.0
    weighted_cos = 0.0

    for idx in range(1, len(trajectory)):
        dx = trajectory[idx][0] - trajectory[idx - 1][0]
        dy = trajectory[idx][1] - trajectory[idx - 1][1]
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1e-6:
            continue
        angle = math.atan2(dy, dx)  # radians, image coords
        weight = idx  # later observations are more reliable
        weighted_sin += weight * math.sin(angle)
        weighted_cos += weight * math.cos(angle)
        total_weight += weight

    if total_weight < 1e-9:
        return None

    avg_angle = math.atan2(weighted_sin / total_weight, weighted_cos / total_weight)
    degrees = math.degrees(avg_angle) % 360.0
    return degrees


def angular_difference(a_deg: float, b_deg: float) -> float:
    """Return the smallest unsigned angle between two bearings (degrees).

    The result is always in ``[0, 180]``.
    """
    diff = abs(a_deg - b_deg) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    return diff


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    """Ray-casting algorithm to test if *point* lies inside a polygon.

    Parameters
    ----------
    polygon:
        Ordered sequence of ``(x, y)`` vertices.  The polygon is
        implicitly closed (last vertex connects to first).
    """
    x, y = point
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

# ---- Backward compatibility aliases / helpers for violation modules ----
compute_iou = iou
is_inside = bbox_contains
bbox_center = bbox_centroid

def vertical_overlap_ratio(a: BBox, b: BBox) -> float:
    """Return the ratio of the vertical intersection to the height of b."""
    y_top = max(a[1], b[1])
    y_bottom = min(a[3], b[3])
    
    intersection_h = max(0.0, y_bottom - y_top)
    height_b = b[3] - b[1]
    
    if height_b <= 0:
        return 0.0
    return intersection_h / height_b


