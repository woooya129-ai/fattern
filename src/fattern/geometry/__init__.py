"""Deterministic geometry helpers for pattern pieces."""

from .polygon import (
    BoundingBox,
    Point,
    PolygonValidationError,
    bounding_box,
    has_self_intersection,
    normalize_ring,
    polygon_area,
    polygon_perimeter,
    points_equal,
    validate_simple_polygon,
)

__all__ = [
    "BoundingBox",
    "Point",
    "PolygonValidationError",
    "bounding_box",
    "has_self_intersection",
    "normalize_ring",
    "polygon_area",
    "polygon_perimeter",
    "points_equal",
    "validate_simple_polygon",
]
