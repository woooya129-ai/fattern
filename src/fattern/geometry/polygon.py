"""Polygon calculations used by the engine.

The functions in this module are deterministic and do not depend on LLM output.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

EPSILON = 1e-9
Point = tuple[float, float]


@dataclass(frozen=True)
class BoundingBox:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


class PolygonValidationError(ValueError):
    """Raised when a polygon cannot be used for deterministic metrics."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def points_equal(left: Point, right: Point) -> bool:
    return abs(left[0] - right[0]) <= EPSILON and abs(left[1] - right[1]) <= EPSILON


def normalize_ring(points: list[Point] | tuple[Point, ...]) -> tuple[Point, ...]:
    ring = tuple(points)
    if len(ring) > 1 and points_equal(ring[0], ring[-1]):
        return ring[:-1]
    return ring


def bounding_box(points: list[Point] | tuple[Point, ...]) -> BoundingBox:
    ring = normalize_ring(points)
    if not ring:
        raise PolygonValidationError("INVALID_POLYGON", "Polygon has no vertices.")

    xs = [point[0] for point in ring]
    ys = [point[1] for point in ring]
    return BoundingBox(min(xs), min(ys), max(xs), max(ys))


def signed_polygon_area(points: list[Point] | tuple[Point, ...]) -> float:
    ring = normalize_ring(points)
    if len(ring) < 3:
        return 0.0

    total = 0.0
    for index, current in enumerate(ring):
        following = ring[(index + 1) % len(ring)]
        total += current[0] * following[1] - following[0] * current[1]
    return total / 2.0


def polygon_area(points: list[Point] | tuple[Point, ...]) -> float:
    return abs(signed_polygon_area(points))


def polygon_perimeter(points: list[Point] | tuple[Point, ...]) -> float:
    ring = normalize_ring(points)
    if len(ring) < 2:
        return 0.0

    total = 0.0
    for index, current in enumerate(ring):
        following = ring[(index + 1) % len(ring)]
        total += hypot(following[0] - current[0], following[1] - current[1])
    return total


def _orientation(a: Point, b: Point, c: Point) -> int:
    cross = (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])
    if abs(cross) <= EPSILON:
        return 0
    return 1 if cross > 0 else 2


def _on_segment(a: Point, b: Point, c: Point) -> bool:
    return (
        min(a[0], c[0]) - EPSILON <= b[0] <= max(a[0], c[0]) + EPSILON
        and min(a[1], c[1]) - EPSILON <= b[1] <= max(a[1], c[1]) + EPSILON
    )


def _segments_intersect(first_a: Point, first_b: Point, second_a: Point, second_b: Point) -> bool:
    orientation_1 = _orientation(first_a, first_b, second_a)
    orientation_2 = _orientation(first_a, first_b, second_b)
    orientation_3 = _orientation(second_a, second_b, first_a)
    orientation_4 = _orientation(second_a, second_b, first_b)

    if orientation_1 != orientation_2 and orientation_3 != orientation_4:
        return True

    return (
        orientation_1 == 0
        and _on_segment(first_a, second_a, first_b)
        or orientation_2 == 0
        and _on_segment(first_a, second_b, first_b)
        or orientation_3 == 0
        and _on_segment(second_a, first_a, second_b)
        or orientation_4 == 0
        and _on_segment(second_a, first_b, second_b)
    )


def has_self_intersection(points: list[Point] | tuple[Point, ...]) -> bool:
    ring = normalize_ring(points)
    edge_count = len(ring)
    if edge_count < 4:
        return False

    for first_index in range(edge_count):
        first_a = ring[first_index]
        first_b = ring[(first_index + 1) % edge_count]
        for second_index in range(first_index + 1, edge_count):
            if abs(first_index - second_index) == 1:
                continue
            if first_index == 0 and second_index == edge_count - 1:
                continue

            second_a = ring[second_index]
            second_b = ring[(second_index + 1) % edge_count]
            if _segments_intersect(first_a, first_b, second_a, second_b):
                return True

    return False


def validate_simple_polygon(points: list[Point] | tuple[Point, ...]) -> tuple[Point, ...]:
    ring = normalize_ring(points)
    if len(ring) < 3:
        raise PolygonValidationError("INVALID_POLYGON", "Polygon requires at least three vertices.")

    if len(set(ring)) != len(ring):
        raise PolygonValidationError("INVALID_POLYGON", "Polygon contains duplicate vertices.")

    if has_self_intersection(ring):
        raise PolygonValidationError("SELF_INTERSECTION", "Polygon edges intersect each other.")

    if polygon_area(ring) <= EPSILON:
        raise PolygonValidationError("INVALID_POLYGON", "Polygon area must be greater than zero.")

    return ring
