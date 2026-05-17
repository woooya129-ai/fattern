"""Deterministic bbox shelf marker layout."""

from __future__ import annotations

from collections.abc import Sequence

from fattern.geometry.polygon import EPSILON
from fattern.schemas import (
    DEFAULT_CLEARANCE_CM,
    DEFAULT_ROTATION_ALLOWED_DEGREES,
    DEFAULT_UNIT,
)

from .models import (
    EngineMessage,
    LayoutOverlap,
    LayoutPlacement,
    LayoutResult,
    LayoutValidity,
    MetricsResult,
    PieceMetrics,
)

VALID_ROTATIONS = (0, 90, 180, 270)


def estimate_bbox_shelf_layout(
    metrics_result: MetricsResult | Sequence[PieceMetrics],
    fabric_width: float,
    rotation_allowed_degrees: Sequence[int] = DEFAULT_ROTATION_ALLOWED_DEGREES,
    clearance: float = DEFAULT_CLEARANCE_CM,
    unit: str = DEFAULT_UNIT,
    fabric_width_unit: str | None = None,
) -> LayoutResult:
    metrics, upstream_messages = _metrics_from_input(metrics_result)
    rotations = _normalize_rotations(rotation_allowed_degrees)
    layout_unit = fabric_width_unit or unit

    if any(message.severity == "blocker" for message in upstream_messages):
        return _blocked_layout_result(fabric_width, clearance, layout_unit, rotations, upstream_messages)

    input_messages = _validate_layout_input(metrics, fabric_width, rotations, clearance, layout_unit)
    if input_messages:
        return _blocked_layout_result(fabric_width, clearance, layout_unit, rotations, input_messages)

    placements: list[LayoutPlacement] = []
    row_x = 0.0
    row_y = 0.0
    row_height = 0.0

    for metric in metrics:
        orientation = _select_orientation(metric, rotations, fabric_width, row_x, clearance)
        if orientation is None and row_x > EPSILON:
            row_x = 0.0
            row_y += row_height + clearance
            row_height = 0.0
            orientation = _select_orientation(metric, rotations, fabric_width, row_x, clearance)

        if orientation is None:
            return _blocked_layout_result(
                fabric_width,
                clearance,
                layout_unit,
                rotations,
                (
                    EngineMessage(
                        code="FABRIC_WIDTH_EXCEEDED",
                        message=f"{metric.piece_id}: bbox width exceeds fabric width for allowed rotations.",
                        severity="blocker",
                    ),
                ),
            )

        width, height = _oriented_dimensions(metric, orientation)
        placement_x = _next_x(row_x, clearance)
        placements.append(
            LayoutPlacement(
                piece_id=metric.piece_id,
                layer=metric.layer,
                x=placement_x,
                y=row_y,
                width=width,
                height=height,
                rotation_degrees=orientation,
            )
        )
        row_x = placement_x + width
        row_height = max(row_height, height)

    marker_length = row_y + row_height if placements else 0.0
    total_piece_area = sum(metric.area for metric in metrics)
    marker_area = fabric_width * marker_length
    efficiency = total_piece_area / marker_area if marker_area > EPSILON else 0.0
    validity, validation_messages = validate_marker_layout(placements, fabric_width)

    return LayoutResult(
        placements=tuple(placements),
        fabric_width=fabric_width,
        marker_length=marker_length,
        efficiency=efficiency,
        clearance=clearance,
        unit=layout_unit,
        no_overlap=validity.no_overlap,
        messages=validation_messages,
        within_fabric_width=validity.within_fabric_width,
        overlaps=validity.overlaps,
        total_piece_area=total_piece_area,
        rotation_allowed_degrees=rotations,
    )


def estimate_marker_layout(
    metrics_result: MetricsResult | Sequence[PieceMetrics],
    fabric_width: float,
    fabric_width_unit: str = DEFAULT_UNIT,
    rotation_allowed_degrees: Sequence[int] = DEFAULT_ROTATION_ALLOWED_DEGREES,
    clearance: float = DEFAULT_CLEARANCE_CM,
) -> LayoutResult:
    return estimate_bbox_shelf_layout(
        metrics_result=metrics_result,
        fabric_width=fabric_width,
        fabric_width_unit=fabric_width_unit,
        rotation_allowed_degrees=rotation_allowed_degrees,
        clearance=clearance,
    )


def validate_marker_layout(
    placements: Sequence[LayoutPlacement],
    fabric_width: float,
) -> tuple[LayoutValidity, tuple[EngineMessage, ...]]:
    width_violations = tuple(
        placement
        for placement in placements
        if placement.x < -EPSILON or placement.right > fabric_width + EPSILON
    )
    overlaps = _find_overlaps(placements)
    messages: list[EngineMessage] = []

    if width_violations:
        piece_ids = ", ".join(placement.piece_id for placement in width_violations)
        messages.append(
            EngineMessage(
                code="FABRIC_WIDTH_EXCEEDED",
                message=f"Layout placements exceed fabric width: {piece_ids}.",
                severity="blocker",
            )
        )

    if overlaps:
        pair_text = ", ".join(f"{overlap.first_piece_id}/{overlap.second_piece_id}" for overlap in overlaps)
        messages.append(
            EngineMessage(
                code="OVERLAP_DETECTED",
                message=f"Layout placements overlap: {pair_text}.",
                severity="blocker",
            )
        )

    return (
        LayoutValidity(
            within_fabric_width=not width_violations,
            no_overlap=not overlaps,
            overlaps=overlaps,
        ),
        tuple(messages),
    )


def validate_no_overlap(placements: Sequence[LayoutPlacement]) -> tuple[EngineMessage, ...]:
    overlaps = _find_overlaps(placements)
    if not overlaps:
        return ()
    pair_text = ", ".join(f"{overlap.first_piece_id}/{overlap.second_piece_id}" for overlap in overlaps)
    return (
        EngineMessage(
            code="OVERLAP_DETECTED",
            message=f"Layout placements overlap: {pair_text}.",
            severity="blocker",
        ),
    )


def _metrics_from_input(
    metrics_result: MetricsResult | Sequence[PieceMetrics],
) -> tuple[tuple[PieceMetrics, ...], tuple[EngineMessage, ...]]:
    if isinstance(metrics_result, MetricsResult):
        return metrics_result.metrics, metrics_result.messages
    return tuple(metrics_result), ()


def _normalize_rotations(rotation_allowed_degrees: Sequence[int]) -> tuple[int, ...]:
    normalized: list[int] = []
    for rotation in rotation_allowed_degrees:
        if rotation not in normalized:
            normalized.append(rotation)
    return tuple(normalized)


def _validate_layout_input(
    metrics: tuple[PieceMetrics, ...],
    fabric_width: float,
    rotation_allowed_degrees: tuple[int, ...],
    clearance: float,
    unit: str,
) -> tuple[EngineMessage, ...]:
    messages: list[EngineMessage] = []

    if not metrics:
        messages.append(EngineMessage(code="NO_METRICS", message="No piece metrics were provided.", severity="blocker"))

    if fabric_width <= EPSILON:
        messages.append(
            EngineMessage(code="INVALID_FABRIC_WIDTH", message="Fabric width must be greater than zero.", severity="blocker")
        )

    if clearance < 0:
        messages.append(
            EngineMessage(code="INVALID_CLEARANCE", message="Clearance must be zero or greater.", severity="blocker")
        )

    if not rotation_allowed_degrees or any(rotation not in VALID_ROTATIONS for rotation in rotation_allowed_degrees):
        messages.append(
            EngineMessage(
                code="INVALID_ROTATION",
                message="Rotation must be one or more of 0, 90, 180, 270 degrees.",
                severity="blocker",
            )
        )

    unit_mismatches = tuple(metric.piece_id for metric in metrics if metric.unit != unit)
    if unit_mismatches:
        messages.append(
            EngineMessage(
                code="UNIT_MISMATCH",
                message=f"Piece metric units do not match fabric width unit: {', '.join(unit_mismatches)}.",
                severity="blocker",
            )
        )

    invalid_bboxes = tuple(
        metric.piece_id
        for metric in metrics
        if metric.bbox.width <= EPSILON or metric.bbox.height <= EPSILON
    )
    if invalid_bboxes:
        messages.append(
            EngineMessage(
                code="INVALID_PIECE_BBOX",
                message=f"Piece metrics contain invalid bbox dimensions: {', '.join(invalid_bboxes)}.",
                severity="blocker",
            )
        )

    return tuple(messages)


def _blocked_layout_result(
    fabric_width: float,
    clearance: float,
    unit: str,
    rotations: tuple[int, ...],
    messages: tuple[EngineMessage, ...],
) -> LayoutResult:
    within_fabric_width = not any(message.code == "FABRIC_WIDTH_EXCEEDED" for message in messages)
    no_overlap = not any(message.code == "OVERLAP_DETECTED" for message in messages)
    return LayoutResult(
        placements=(),
        fabric_width=fabric_width,
        marker_length=0.0,
        efficiency=0.0,
        clearance=clearance,
        unit=unit,
        no_overlap=no_overlap,
        messages=messages,
        within_fabric_width=within_fabric_width,
        overlaps=(),
        total_piece_area=0.0,
        rotation_allowed_degrees=rotations,
    )


def _select_orientation(
    metric: PieceMetrics,
    rotation_allowed_degrees: tuple[int, ...],
    fabric_width: float,
    row_x: float,
    clearance: float,
) -> int | None:
    placement_x = _next_x(row_x, clearance)
    for rotation in rotation_allowed_degrees:
        width, _height = _oriented_dimensions(metric, rotation)
        if placement_x + width <= fabric_width + EPSILON:
            return rotation
    return None


def _oriented_dimensions(metric: PieceMetrics, rotation_degrees: int) -> tuple[float, float]:
    if rotation_degrees in (90, 270):
        return metric.bbox.height, metric.bbox.width
    return metric.bbox.width, metric.bbox.height


def _next_x(row_x: float, clearance: float) -> float:
    if row_x <= EPSILON:
        return 0.0
    return row_x + clearance


def _find_overlaps(placements: Sequence[LayoutPlacement]) -> tuple[LayoutOverlap, ...]:
    overlaps: list[LayoutOverlap] = []
    for first_index, first in enumerate(placements):
        for second in placements[first_index + 1 :]:
            if _rectangles_overlap(first, second):
                overlaps.append(LayoutOverlap(first_piece_id=first.piece_id, second_piece_id=second.piece_id))
    return tuple(overlaps)


def _rectangles_overlap(first: LayoutPlacement, second: LayoutPlacement) -> bool:
    separated = (
        first.right <= second.x + EPSILON
        or second.right <= first.x + EPSILON
        or first.bottom <= second.y + EPSILON
        or second.bottom <= first.y + EPSILON
    )
    return not separated
