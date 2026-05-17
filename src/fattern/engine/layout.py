"""Deterministic bbox-based marker layout."""

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
COMPACT_LAYOUT_BEAM_WIDTH = 24
MAX_CANDIDATE_PLACEMENTS_PER_STATE = 32
COORDINATE_KEY_PRECISION = 9


def estimate_compact_bbox_layout(
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

    placements = _best_compact_layout(metrics, rotations, fabric_width, clearance)
    if placements is None:
        blocked_piece = _first_piece_exceeding_width(metrics, rotations, fabric_width)
        piece_id = blocked_piece.piece_id if blocked_piece is not None else "piece"
        return _blocked_layout_result(
            fabric_width,
            clearance,
            layout_unit,
            rotations,
            (
                EngineMessage(
                    code="FABRIC_WIDTH_EXCEEDED",
                    message=f"{piece_id}: bbox width exceeds fabric width for allowed rotations.",
                    severity="blocker",
                ),
            ),
        )

    marker_length = _marker_length(placements)
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
    return estimate_compact_bbox_layout(
        metrics_result=metrics_result,
        fabric_width=fabric_width,
        fabric_width_unit=fabric_width_unit,
        rotation_allowed_degrees=rotation_allowed_degrees,
        clearance=clearance,
    )


def estimate_bbox_shelf_layout(
    metrics_result: MetricsResult | Sequence[PieceMetrics],
    fabric_width: float,
    rotation_allowed_degrees: Sequence[int] = DEFAULT_ROTATION_ALLOWED_DEGREES,
    clearance: float = DEFAULT_CLEARANCE_CM,
    unit: str = DEFAULT_UNIT,
    fabric_width_unit: str | None = None,
) -> LayoutResult:
    """Backward-compatible alias for the compact bbox layout engine."""

    return estimate_compact_bbox_layout(
        metrics_result=metrics_result,
        fabric_width=fabric_width,
        rotation_allowed_degrees=rotation_allowed_degrees,
        clearance=clearance,
        unit=unit,
        fabric_width_unit=fabric_width_unit,
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


def _best_compact_layout(
    metrics: tuple[PieceMetrics, ...],
    rotations: tuple[int, ...],
    fabric_width: float,
    clearance: float,
) -> tuple[LayoutPlacement, ...] | None:
    layouts: list[tuple[int, tuple[LayoutPlacement, ...]]] = []
    for order_index, ordered_metrics in enumerate(_metric_orders(metrics)):
        placements = _place_bottom_left(ordered_metrics, rotations, fabric_width, clearance)
        if placements is not None:
            layouts.append((order_index, placements))

    if not layouts:
        return None

    _order_index, best = min(layouts, key=lambda item: _layout_score(item[1], item[0]))
    return best


def _metric_orders(metrics: tuple[PieceMetrics, ...]) -> tuple[tuple[PieceMetrics, ...], ...]:
    indexed = tuple(enumerate(metrics))
    ordered: list[tuple[PieceMetrics, ...]] = []
    seen: set[tuple[str, ...]] = set()

    def add(items: tuple[tuple[int, PieceMetrics], ...]) -> None:
        sequence = tuple(metric for _index, metric in items)
        key = tuple(metric.piece_id for metric in sequence)
        if key in seen:
            return
        ordered.append(sequence)
        seen.add(key)

    add(indexed)
    add(tuple(sorted(indexed, key=lambda item: (-item[1].area, -max(item[1].bbox.width, item[1].bbox.height), item[0]))))
    add(tuple(sorted(indexed, key=lambda item: (-max(item[1].bbox.width, item[1].bbox.height), -item[1].area, item[0]))))
    add(tuple(sorted(indexed, key=lambda item: (-item[1].bbox.height, -item[1].bbox.width, item[0]))))
    add(tuple(sorted(indexed, key=lambda item: (-item[1].bbox.width, -item[1].bbox.height, item[0]))))
    return tuple(ordered)


def _place_bottom_left(
    metrics: tuple[PieceMetrics, ...],
    rotations: tuple[int, ...],
    fabric_width: float,
    clearance: float,
) -> tuple[LayoutPlacement, ...] | None:
    states: tuple[tuple[LayoutPlacement, ...], ...] = ((),)
    for metric in metrics:
        ranked_states: list[tuple[tuple[float, float, float, int, int], tuple[LayoutPlacement, ...]]] = []
        for parent_rank, placements in enumerate(states):
            candidates = _candidate_placements(metric, placements, rotations, fabric_width, clearance)
            for candidate_rank, placement in enumerate(candidates):
                next_placements = (*placements, placement)
                ranked_states.append(
                    (_partial_layout_score(next_placements, parent_rank, candidate_rank), next_placements)
                )

        if not ranked_states:
            return None

        states = _trim_ranked_layouts(ranked_states, COMPACT_LAYOUT_BEAM_WIDTH)

    return min(states, key=lambda placements: _layout_score(placements, 0))


def _find_bottom_left_position(
    metric: PieceMetrics,
    placements: Sequence[LayoutPlacement],
    rotations: tuple[int, ...],
    fabric_width: float,
    clearance: float,
) -> LayoutPlacement | None:
    candidates = _candidate_placements(metric, placements, rotations, fabric_width, clearance)
    return candidates[0] if candidates else None


def _candidate_placements(
    metric: PieceMetrics,
    placements: Sequence[LayoutPlacement],
    rotations: tuple[int, ...],
    fabric_width: float,
    clearance: float,
) -> tuple[LayoutPlacement, ...]:
    ranked: list[tuple[tuple[float, float, float, float, int], LayoutPlacement]] = []

    for rotation_index, rotation in enumerate(rotations):
        width, height = _oriented_dimensions(metric, rotation)
        if width > fabric_width + EPSILON:
            continue
        x_candidates, y_candidates = _candidate_coordinates(placements, clearance, width, height, fabric_width)
        for y in y_candidates:
            for x in x_candidates:
                if x + width > fabric_width + EPSILON:
                    continue
                candidate = LayoutPlacement(
                    piece_id=metric.piece_id,
                    layer=metric.layer,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    rotation_degrees=rotation,
                )
                if _has_clearance_conflict(candidate, placements, clearance):
                    continue
                score = _placement_score(placements, candidate, fabric_width, clearance, rotation_index)
                ranked.append((score, candidate))

    return _trim_ranked_placements(ranked, MAX_CANDIDATE_PLACEMENTS_PER_STATE)


def _candidate_coordinates(
    placements: Sequence[LayoutPlacement],
    clearance: float,
    width: float,
    height: float,
    fabric_width: float,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    x_values = {0.0, fabric_width - width}
    y_values = {0.0}
    for placement in placements:
        x_values.add(_clean_coordinate(placement.x))
        x_values.add(_clean_coordinate(placement.right + clearance))
        x_values.add(_clean_coordinate(placement.x - clearance - width))
        x_values.add(_clean_coordinate(placement.right - width))
        y_values.add(_clean_coordinate(placement.y))
        y_values.add(_clean_coordinate(placement.bottom + clearance))
        y_values.add(_clean_coordinate(placement.y - clearance - height))
        y_values.add(_clean_coordinate(placement.bottom - height))
    max_x = fabric_width - width
    return _bounded_coordinates(x_values, max_x), _bounded_coordinates(y_values, None)


def _has_clearance_conflict(
    candidate: LayoutPlacement,
    placements: Sequence[LayoutPlacement],
    clearance: float,
) -> bool:
    return any(_rectangles_overlap_with_clearance(candidate, placed, clearance) for placed in placements)


def _rectangles_overlap_with_clearance(
    first: LayoutPlacement,
    second: LayoutPlacement,
    clearance: float,
) -> bool:
    separated = (
        first.right + clearance <= second.x + EPSILON
        or second.right + clearance <= first.x + EPSILON
        or first.bottom + clearance <= second.y + EPSILON
        or second.bottom + clearance <= first.y + EPSILON
    )
    return not separated


def _first_piece_exceeding_width(
    metrics: tuple[PieceMetrics, ...],
    rotations: tuple[int, ...],
    fabric_width: float,
) -> PieceMetrics | None:
    for metric in metrics:
        if all(_oriented_dimensions(metric, rotation)[0] > fabric_width + EPSILON for rotation in rotations):
            return metric
    return None


def _layout_score(placements: tuple[LayoutPlacement, ...], order_index: int) -> tuple[float, float, float, int]:
    return (
        _marker_length(placements),
        sum(placement.y for placement in placements),
        max((placement.right for placement in placements), default=0.0),
        order_index,
    )


def _partial_layout_score(
    placements: tuple[LayoutPlacement, ...],
    parent_rank: int,
    candidate_rank: int,
) -> tuple[float, float, float, int, int]:
    return (
        _marker_length(placements),
        sum(placement.y for placement in placements),
        max((placement.right for placement in placements), default=0.0),
        parent_rank,
        candidate_rank,
    )


def _placement_score(
    placements: Sequence[LayoutPlacement],
    candidate: LayoutPlacement,
    fabric_width: float,
    clearance: float,
    rotation_index: int,
) -> tuple[float, float, float, float, int]:
    return (
        max(_marker_length(placements), candidate.bottom),
        -_contact_score(candidate, placements, fabric_width, clearance),
        candidate.y,
        candidate.x,
        rotation_index,
    )


def _contact_score(
    candidate: LayoutPlacement,
    placements: Sequence[LayoutPlacement],
    fabric_width: float,
    clearance: float,
) -> float:
    score = 0.0
    if abs(candidate.x) <= EPSILON:
        score += candidate.height
    if abs(candidate.right - fabric_width) <= EPSILON:
        score += candidate.height
    if abs(candidate.y) <= EPSILON:
        score += candidate.width

    for placement in placements:
        vertical_overlap = _overlap_length(candidate.y, candidate.bottom, placement.y, placement.bottom)
        horizontal_overlap = _overlap_length(candidate.x, candidate.right, placement.x, placement.right)
        if vertical_overlap > EPSILON and (
            abs(candidate.x - (placement.right + clearance)) <= EPSILON
            or abs(placement.x - (candidate.right + clearance)) <= EPSILON
        ):
            score += vertical_overlap
        if horizontal_overlap > EPSILON and (
            abs(candidate.y - (placement.bottom + clearance)) <= EPSILON
            or abs(placement.y - (candidate.bottom + clearance)) <= EPSILON
        ):
            score += horizontal_overlap

    return score


def _overlap_length(first_start: float, first_end: float, second_start: float, second_end: float) -> float:
    return max(0.0, min(first_end, second_end) - max(first_start, second_start))


def _trim_ranked_layouts(
    ranked_states: list[tuple[tuple[float, float, float, int, int], tuple[LayoutPlacement, ...]]],
    limit: int,
) -> tuple[tuple[LayoutPlacement, ...], ...]:
    states: list[tuple[LayoutPlacement, ...]] = []
    seen: set[tuple[tuple[str, float, float, float, float], ...]] = set()
    for _score, placements in sorted(ranked_states, key=lambda item: item[0]):
        key = _layout_state_key(placements)
        if key in seen:
            continue
        states.append(placements)
        seen.add(key)
        if len(states) >= limit:
            break
    return tuple(states)


def _trim_ranked_placements(
    ranked: list[tuple[tuple[float, float, float, float, int], LayoutPlacement]],
    limit: int,
) -> tuple[LayoutPlacement, ...]:
    placements: list[LayoutPlacement] = []
    seen: set[tuple[str, float, float, float, float]] = set()
    for _score, placement in sorted(ranked, key=lambda item: item[0]):
        key = _placement_geometry_key(placement)
        if key in seen:
            continue
        placements.append(placement)
        seen.add(key)
        if len(placements) >= limit:
            break
    return tuple(placements)


def _layout_state_key(
    placements: tuple[LayoutPlacement, ...],
) -> tuple[tuple[str, float, float, float, float], ...]:
    return tuple(_placement_geometry_key(placement) for placement in placements)


def _placement_geometry_key(placement: LayoutPlacement) -> tuple[str, float, float, float, float]:
    return (
        placement.piece_id,
        round(placement.x, COORDINATE_KEY_PRECISION),
        round(placement.y, COORDINATE_KEY_PRECISION),
        round(placement.width, COORDINATE_KEY_PRECISION),
        round(placement.height, COORDINATE_KEY_PRECISION),
    )


def _bounded_coordinates(values: set[float], upper_bound: float | None) -> tuple[float, ...]:
    bounded: set[float] = set()
    for value in values:
        if value < -EPSILON:
            continue
        if upper_bound is not None and value > upper_bound + EPSILON:
            continue
        bounded.add(_clean_coordinate(value))
    return tuple(sorted(bounded))


def _marker_length(placements: Sequence[LayoutPlacement]) -> float:
    return max((placement.bottom for placement in placements), default=0.0)


def _clean_coordinate(value: float) -> float:
    return 0.0 if abs(value) <= EPSILON else value


def _oriented_dimensions(metric: PieceMetrics, rotation_degrees: int) -> tuple[float, float]:
    if rotation_degrees in (90, 270):
        return metric.bbox.height, metric.bbox.width
    return metric.bbox.width, metric.bbox.height


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
