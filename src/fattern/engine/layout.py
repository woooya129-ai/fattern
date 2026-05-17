"""Deterministic polygon-aware marker layout."""

from __future__ import annotations

from collections.abc import Sequence
from math import hypot

from fattern.geometry import Point
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
NON_ONE_WAY_NAP_DIRECTIONS = {"two_way", "none", "no_nap", "not_one_way"}
VALID_GRAINLINE_STATUSES = {"present", "missing", "unknown"}
VALID_FABRIC_TYPES = {"woven", "knit", "unknown"}
COMPACT_LAYOUT_BEAM_WIDTH = 4
MAX_CANDIDATE_PLACEMENTS_PER_STATE = 6
MAX_COLLISION_OUTLINE_POINTS = 96
COMPLEX_OUTLINE_POINT_THRESHOLD = 600
CONTACT_CLEARANCE_MULTIPLIERS = (1.0, 2.0)
MAX_X_COORDINATE_CANDIDATES = 28
MAX_Y_COORDINATE_CANDIDATES = 28
COORDINATE_KEY_PRECISION = 9


def estimate_compact_bbox_layout(
    metrics_result: MetricsResult | Sequence[PieceMetrics],
    fabric_width: float,
    rotation_allowed_degrees: Sequence[int] = DEFAULT_ROTATION_ALLOWED_DEGREES,
    clearance: float = DEFAULT_CLEARANCE_CM,
    unit: str = DEFAULT_UNIT,
    fabric_width_unit: str | None = None,
    cuttable_width: float | None = None,
    spacing: float | None = None,
    nap_direction: str | None = None,
    one_way_fabric: bool | None = None,
    grainline_status: str = "unknown",
    grainline_required: bool | None = None,
    fabric_type: str | None = None,
) -> LayoutResult:
    metrics, upstream_messages = _metrics_from_input(metrics_result)
    input_rotations = _normalize_rotations(rotation_allowed_degrees)
    layout_unit = fabric_width_unit or unit
    resolved_fabric_width, width_messages = _resolve_fabric_width(fabric_width, cuttable_width)
    resolved_clearance, spacing_messages = _resolve_clearance(clearance, spacing)
    resolved_nap_direction, nap_messages = _resolve_nap_direction(nap_direction)
    rotations, rotation_policy_messages = _apply_nap_rotation_policy(
        input_rotations,
        resolved_nap_direction,
        one_way_fabric,
    )
    resolved_grainline_status, grainline_messages = _resolve_grainline_status(grainline_status)
    resolved_grainline_required, grainline_required_messages = _resolve_grainline_required(grainline_required)
    resolved_fabric_type, fabric_type_messages = _resolve_fabric_type(fabric_type)
    policy_messages = (
        *width_messages,
        *spacing_messages,
        *nap_messages,
        *rotation_policy_messages,
        *grainline_messages,
        *grainline_required_messages,
        *fabric_type_messages,
    )

    if any(message.severity == "blocker" for message in upstream_messages):
        return _blocked_layout_result(fabric_width, clearance, layout_unit, input_rotations, upstream_messages)

    grainline_policy_messages = _grainline_policy_messages(
        resolved_grainline_required,
        resolved_fabric_type,
        one_way_fabric,
        resolved_grainline_status,
    )
    combined_policy_messages = (*policy_messages, *grainline_policy_messages)
    if any(message.severity == "blocker" for message in combined_policy_messages):
        return _blocked_layout_result(
            resolved_fabric_width,
            resolved_clearance,
            layout_unit,
            rotations,
            combined_policy_messages,
        )

    input_messages = _validate_layout_input(metrics, resolved_fabric_width, rotations, resolved_clearance, layout_unit)
    if input_messages:
        return _blocked_layout_result(
            resolved_fabric_width,
            resolved_clearance,
            layout_unit,
            rotations,
            (*combined_policy_messages, *input_messages),
        )

    layout = _best_compact_layout(metrics, rotations, resolved_fabric_width, resolved_clearance)
    if layout is None:
        blocked_piece = _first_piece_exceeding_width(metrics, rotations, resolved_fabric_width)
        piece_id = blocked_piece.piece_id if blocked_piece is not None else "piece"
        return _blocked_layout_result(
            resolved_fabric_width,
            resolved_clearance,
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
    placements, used_bbox_fallback = layout

    marker_length = _marker_length(placements)
    total_piece_area = sum(metric.area for metric in metrics)
    marker_area = resolved_fabric_width * marker_length
    efficiency = total_piece_area / marker_area if marker_area > EPSILON else 0.0
    validity, validation_messages = validate_marker_layout(placements, resolved_fabric_width, resolved_clearance)
    layout_messages = _layout_messages(used_bbox_fallback)

    return LayoutResult(
        placements=tuple(placements),
        fabric_width=resolved_fabric_width,
        marker_length=marker_length,
        efficiency=efficiency,
        clearance=resolved_clearance,
        unit=layout_unit,
        no_overlap=validity.no_overlap,
        messages=(*combined_policy_messages, *layout_messages, *validation_messages),
        within_fabric_width=validity.within_fabric_width,
        overlaps=validity.overlaps,
        total_piece_area=total_piece_area,
        rotation_allowed_degrees=rotations,
        grainline_status=resolved_grainline_status,
        one_way_fabric=one_way_fabric,
    )


def estimate_marker_layout(
    metrics_result: MetricsResult | Sequence[PieceMetrics],
    fabric_width: float,
    fabric_width_unit: str = DEFAULT_UNIT,
    rotation_allowed_degrees: Sequence[int] = DEFAULT_ROTATION_ALLOWED_DEGREES,
    clearance: float = DEFAULT_CLEARANCE_CM,
    cuttable_width: float | None = None,
    spacing: float | None = None,
    nap_direction: str | None = None,
    one_way_fabric: bool | None = None,
    grainline_status: str = "unknown",
    grainline_required: bool | None = None,
    fabric_type: str | None = None,
) -> LayoutResult:
    return estimate_compact_bbox_layout(
        metrics_result=metrics_result,
        fabric_width=fabric_width,
        fabric_width_unit=fabric_width_unit,
        rotation_allowed_degrees=rotation_allowed_degrees,
        clearance=clearance,
        cuttable_width=cuttable_width,
        spacing=spacing,
        nap_direction=nap_direction,
        one_way_fabric=one_way_fabric,
        grainline_status=grainline_status,
        grainline_required=grainline_required,
        fabric_type=fabric_type,
    )


def estimate_bbox_shelf_layout(
    metrics_result: MetricsResult | Sequence[PieceMetrics],
    fabric_width: float,
    rotation_allowed_degrees: Sequence[int] = DEFAULT_ROTATION_ALLOWED_DEGREES,
    clearance: float = DEFAULT_CLEARANCE_CM,
    unit: str = DEFAULT_UNIT,
    fabric_width_unit: str | None = None,
    cuttable_width: float | None = None,
    spacing: float | None = None,
    nap_direction: str | None = None,
    one_way_fabric: bool | None = None,
    grainline_status: str = "unknown",
    grainline_required: bool | None = None,
    fabric_type: str | None = None,
) -> LayoutResult:
    """Backward-compatible alias for the compact bbox layout engine."""

    return estimate_compact_bbox_layout(
        metrics_result=metrics_result,
        fabric_width=fabric_width,
        rotation_allowed_degrees=rotation_allowed_degrees,
        clearance=clearance,
        unit=unit,
        fabric_width_unit=fabric_width_unit,
        cuttable_width=cuttable_width,
        spacing=spacing,
        nap_direction=nap_direction,
        one_way_fabric=one_way_fabric,
        grainline_status=grainline_status,
        grainline_required=grainline_required,
        fabric_type=fabric_type,
    )


def validate_marker_layout(
    placements: Sequence[LayoutPlacement],
    fabric_width: float,
    clearance: float = 0.0,
) -> tuple[LayoutValidity, tuple[EngineMessage, ...]]:
    width_violations = tuple(
        placement
        for placement in placements
        if placement.x < -EPSILON or placement.right > fabric_width + EPSILON
    )
    overlaps = _find_overlaps(placements, clearance)
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


def validate_no_overlap(placements: Sequence[LayoutPlacement], clearance: float = 0.0) -> tuple[EngineMessage, ...]:
    overlaps = _find_overlaps(placements, clearance)
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


def _resolve_fabric_width(fabric_width: float, cuttable_width: float | None) -> tuple[float, tuple[EngineMessage, ...]]:
    if cuttable_width is None:
        return fabric_width, ()
    if cuttable_width <= EPSILON:
        return (
            fabric_width,
            (
                EngineMessage(
                    code="INVALID_CUTTABLE_WIDTH",
                    message="cuttable_width must be greater than zero.",
                    severity="blocker",
                ),
            ),
        )

    messages: list[EngineMessage] = []
    if cuttable_width > fabric_width + EPSILON:
        return (
            fabric_width,
            (
                EngineMessage(
                    code="INVALID_CUTTABLE_WIDTH",
                    message="cuttable_width must not be greater than fabric_width.",
                    severity="blocker",
                ),
            ),
        )
    if abs(cuttable_width - fabric_width) > EPSILON:
        messages.append(
            EngineMessage(
                code="CUTTABLE_WIDTH_APPLIED",
                message="cuttable_width was prioritized over fabric_width for layout width.",
                severity="warning",
            )
        )

    return cuttable_width, tuple(messages)


def _resolve_clearance(clearance: float, spacing: float | None) -> tuple[float, tuple[EngineMessage, ...]]:
    if spacing is None:
        return clearance, ()
    if spacing < 0:
        return (
            clearance,
            (
                EngineMessage(
                    code="INVALID_SPACING",
                    message="spacing must be zero or greater.",
                    severity="blocker",
                ),
            ),
        )
    if abs(clearance - spacing) <= EPSILON:
        return spacing, ()
    return (
        spacing,
        (
            EngineMessage(
                code="SPACING_OVERRIDES_CLEARANCE",
                message="spacing was applied as the minimum piece gap and overrides clearance.",
                severity="warning",
            ),
        ),
    )


def _resolve_nap_direction(nap_direction: str | None) -> tuple[str | None, tuple[EngineMessage, ...]]:
    if nap_direction is None:
        return None, ()
    if not isinstance(nap_direction, str):
        return (
            None,
            (
                EngineMessage(
                    code="UNSUPPORTED_NAP_DIRECTION",
                    message="nap_direction is not supported by the engine policy.",
                    severity="blocker",
                ),
            ),
        )
    normalized = nap_direction.strip().lower()
    if normalized == "one_way":
        return normalized, ()
    if normalized in NON_ONE_WAY_NAP_DIRECTIONS:
        return normalized, ()
    return (
        None,
        (
            EngineMessage(
                code="UNSUPPORTED_NAP_DIRECTION",
                message="nap_direction is not supported by the engine policy.",
                severity="blocker",
            ),
        ),
    )


def _apply_nap_rotation_policy(
    rotations: tuple[int, ...],
    nap_direction: str | None,
    one_way_fabric: bool | None,
) -> tuple[tuple[int, ...], tuple[EngineMessage, ...]]:
    if nap_direction != "one_way" and one_way_fabric is not True:
        return rotations, ()
    if 180 not in rotations:
        return rotations, ()
    filtered = tuple(rotation for rotation in rotations if rotation != 180)
    return (
        filtered,
        (
            EngineMessage(
                code="NAP_DIRECTION_ONE_WAY_BLOCKED_180_ROTATION",
                message="180 degree rotation was removed for one-way nap rotation policy.",
                severity="warning",
            ),
        ),
    )


def _resolve_grainline_status(grainline_status: str | None) -> tuple[str, tuple[EngineMessage, ...]]:
    if grainline_status is None:
        return "unknown", ()
    if not isinstance(grainline_status, str):
        return (
            "unknown",
            (
                EngineMessage(
                    code="INVALID_GRAINLINE_STATUS",
                    message="grainline_status must be one of present, missing, unknown.",
                    severity="blocker",
                ),
            ),
        )
    normalized = grainline_status.strip().lower()
    if normalized in VALID_GRAINLINE_STATUSES:
        return normalized, ()
    return (
        "unknown",
        (
            EngineMessage(
                code="INVALID_GRAINLINE_STATUS",
                message="grainline_status must be one of present, missing, unknown.",
                severity="blocker",
            ),
        ),
    )


def _resolve_grainline_required(grainline_required: bool | None) -> tuple[bool, tuple[EngineMessage, ...]]:
    if grainline_required is None:
        return False, ()
    if isinstance(grainline_required, bool):
        return grainline_required, ()
    return (
        False,
        (
            EngineMessage(
                code="INVALID_GRAINLINE_REQUIRED",
                message="grainline_required must be a boolean.",
                severity="blocker",
            ),
        ),
    )


def _resolve_fabric_type(fabric_type: str | None) -> tuple[str, tuple[EngineMessage, ...]]:
    if fabric_type is None:
        return "unknown", ()
    if not isinstance(fabric_type, str):
        return (
            "unknown",
            (
                EngineMessage(
                    code="UNSUPPORTED_FABRIC_TYPE",
                    message="fabric_type must be one of woven, knit, unknown.",
                    severity="blocker",
                ),
            ),
        )
    normalized = fabric_type.strip().lower()
    if normalized in VALID_FABRIC_TYPES:
        return normalized, ()
    return (
        "unknown",
        (
            EngineMessage(
                code="UNSUPPORTED_FABRIC_TYPE",
                message="fabric_type must be one of woven, knit, unknown.",
                severity="blocker",
            ),
        ),
    )


def _grainline_policy_messages(
    grainline_required: bool,
    fabric_type: str,
    one_way_fabric: bool | None,
    grainline_status: str,
) -> tuple[EngineMessage, ...]:
    if grainline_status != "missing":
        return ()
    if grainline_required:
        return (
            EngineMessage(
                code="MISSING_GRAINLINE_REQUIRED",
                message="Grainline is required before estimating marker layout.",
                severity="blocker",
            ),
        )
    if fabric_type == "woven":
        return (
            EngineMessage(
                code="MISSING_GRAINLINE_FOR_WOVEN",
                message="fabric_type=woven requires grainline before estimating marker layout.",
                severity="blocker",
            ),
        )
    if one_way_fabric is True:
        return (
            EngineMessage(
                code="MISSING_GRAINLINE_ON_ONE_WAY_FABRIC",
                message="Grainline must be present for one-way fabric before estimating marker layout.",
                severity="blocker",
            ),
        )
    return ()


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


def _layout_messages(used_bbox_fallback: bool) -> tuple[EngineMessage, ...]:
    if not used_bbox_fallback:
        return ()
    return (
        EngineMessage(
            code="BBOX_FALLBACK_USED",
            message="Polygon-aware compact search did not pass full-outline validation; bbox fallback layout was used.",
            severity="warning",
        ),
    )


def _best_compact_layout(
    metrics: tuple[PieceMetrics, ...],
    rotations: tuple[int, ...],
    fabric_width: float,
    clearance: float,
) -> tuple[tuple[LayoutPlacement, ...], bool] | None:
    layouts: list[tuple[int, tuple[LayoutPlacement, ...], bool]] = []
    fallback = _place_bbox_shelf_layout(metrics, rotations, fabric_width, clearance)
    if fallback is not None:
        layouts.append((len(_metric_orders(metrics)), fallback, True))

    for order_index, ordered_metrics in enumerate(_metric_orders_for_layout(metrics)):
        placements = _place_bottom_left(ordered_metrics, rotations, fabric_width, clearance)
        if placements is not None:
            refined = _refine_compact_layout(placements, fabric_width, clearance)
            layouts.append((order_index, refined, False))

    if not layouts:
        return None

    _order_index, best, used_bbox_fallback = min(layouts, key=lambda item: _layout_score(item[1], item[0]))
    return best, used_bbox_fallback


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
    add(tuple(sorted(indexed, key=lambda item: (-_packing_difficulty(item[1]), item[0]))))
    add(tuple(sorted(indexed, key=lambda item: (-item[1].bbox.height, -item[1].bbox.width, item[0]))))
    add(tuple(sorted(indexed, key=lambda item: (-item[1].bbox.width, -item[1].bbox.height, item[0]))))
    return tuple(ordered)


def _packing_difficulty(metric: PieceMetrics) -> float:
    major = max(metric.bbox.width, metric.bbox.height)
    minor = max(min(metric.bbox.width, metric.bbox.height), EPSILON)
    aspect = major / minor
    area = max(metric.area, EPSILON)
    outline_complexity = metric.perimeter * major / area
    return metric.area * (1.0 + aspect * 0.15 + outline_complexity * 0.05)


def _metric_orders_for_layout(metrics: tuple[PieceMetrics, ...]) -> tuple[tuple[PieceMetrics, ...], ...]:
    orders = _metric_orders(metrics)
    if sum(len(metric.points) for metric in metrics) > COMPLEX_OUTLINE_POINT_THRESHOLD:
        return orders[:1]
    return orders


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

    exact_states = tuple(placements for placements in states if not _find_overlaps(placements, clearance))
    if not exact_states:
        return None
    return min(exact_states, key=lambda placements: _layout_score(placements, 0))


def _place_bbox_shelf_layout(
    metrics: tuple[PieceMetrics, ...],
    rotations: tuple[int, ...],
    fabric_width: float,
    clearance: float,
) -> tuple[LayoutPlacement, ...] | None:
    placements: list[LayoutPlacement] = []
    row_x = 0.0
    row_y = 0.0
    row_height = 0.0

    for metric in metrics:
        orientation = _select_bbox_orientation(metric, rotations, fabric_width, row_x, clearance)
        if orientation is None and row_x > EPSILON:
            row_x = 0.0
            row_y += row_height + clearance
            row_height = 0.0
            orientation = _select_bbox_orientation(metric, rotations, fabric_width, row_x, clearance)

        if orientation is None:
            return None

        width, height = _oriented_dimensions(metric, orientation)
        placement_x = _next_shelf_x(row_x, clearance)
        outline_points = _oriented_outline_points(metric, orientation)
        placements.append(
            LayoutPlacement(
                piece_id=metric.piece_id,
                layer=metric.layer,
                x=placement_x,
                y=row_y,
                width=width,
                height=height,
                rotation_degrees=orientation,
                outline_points=outline_points,
                collision_points=_downsample_outline_points(outline_points, MAX_COLLISION_OUTLINE_POINTS),
            )
        )
        row_x = placement_x + width
        row_height = max(row_height, height)

    return tuple(placements)


def _refine_compact_layout(
    placements: tuple[LayoutPlacement, ...],
    fabric_width: float,
    clearance: float,
) -> tuple[LayoutPlacement, ...]:
    current = placements
    for _pass in range(2):
        changed = False
        for index in _refinement_order(current):
            placement = current[index]
            others = (*current[:index], *current[index + 1 :])
            replacement = _best_refined_placement(placement, others, fabric_width, clearance)
            if replacement is placement:
                continue
            next_layout = (*current[:index], replacement, *current[index + 1 :])
            if _layout_score(next_layout, 0) < _layout_score(current, 0):
                current = next_layout
                changed = True
        if not changed:
            break
    return current


def _refinement_order(placements: tuple[LayoutPlacement, ...]) -> tuple[int, ...]:
    return tuple(
        index
        for index, _placement in sorted(
            enumerate(placements),
            key=lambda item: (-item[1].bottom, -item[1].y, -item[1].right, item[0]),
        )
    )


def _best_refined_placement(
    placement: LayoutPlacement,
    others: tuple[LayoutPlacement, ...],
    fabric_width: float,
    clearance: float,
) -> LayoutPlacement:
    best = placement
    best_score = _layout_score((*others, placement), 0)
    x_candidates, y_candidates = _refinement_coordinates(placement, others, fabric_width, clearance)
    for y in y_candidates:
        if y > placement.y + EPSILON:
            continue
        for x in x_candidates:
            if x + placement.width > fabric_width + EPSILON:
                continue
            candidate = _move_placement(placement, x, y)
            if _has_exact_clearance_conflict(candidate, others, clearance):
                continue
            score = _layout_score((*others, candidate), 0)
            if score < best_score:
                best = candidate
                best_score = score
    return best


def _refinement_coordinates(
    placement: LayoutPlacement,
    others: tuple[LayoutPlacement, ...],
    fabric_width: float,
    clearance: float,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    x_values, y_values = _candidate_coordinates(others, clearance, placement.width, placement.height, fabric_width)
    return (
        tuple(sorted({*x_values, _clean_coordinate(placement.x)})),
        tuple(sorted({*y_values, _clean_coordinate(placement.y)})),
    )


def _has_exact_clearance_conflict(
    candidate: LayoutPlacement,
    placements: Sequence[LayoutPlacement],
    clearance: float,
) -> bool:
    return any(_placements_conflict_for_validation(candidate, placed, clearance) for placed in placements)


def _move_placement(placement: LayoutPlacement, x: float, y: float) -> LayoutPlacement:
    return LayoutPlacement(
        piece_id=placement.piece_id,
        layer=placement.layer,
        x=_clean_coordinate(x),
        y=_clean_coordinate(y),
        width=placement.width,
        height=placement.height,
        rotation_degrees=placement.rotation_degrees,
        outline_points=placement.outline_points,
        collision_points=placement.collision_points,
    )


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
        outline_points = _oriented_outline_points(metric, rotation)
        collision_points = _downsample_outline_points(outline_points, MAX_COLLISION_OUTLINE_POINTS)
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
                    outline_points=outline_points,
                    collision_points=collision_points,
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
        x_values.add(_clean_coordinate(placement.right - width))
        y_values.add(_clean_coordinate(placement.y))
        y_values.add(_clean_coordinate(placement.bottom - height))
        for multiplier in CONTACT_CLEARANCE_MULTIPLIERS:
            gap = clearance * multiplier
            x_values.add(_clean_coordinate(placement.right + gap))
            x_values.add(_clean_coordinate(placement.x - gap - width))
            y_values.add(_clean_coordinate(placement.bottom + gap))
            y_values.add(_clean_coordinate(placement.y - gap - height))
    max_x = fabric_width - width
    return (
        _bounded_coordinates(x_values, max_x, limit=MAX_X_COORDINATE_CANDIDATES),
        _bounded_coordinates(y_values, None, limit=MAX_Y_COORDINATE_CANDIDATES),
    )


def _has_clearance_conflict(
    candidate: LayoutPlacement,
    placements: Sequence[LayoutPlacement],
    clearance: float,
) -> bool:
    return any(_placements_conflict_with_clearance(candidate, placed, clearance) for placed in placements)


def _placements_conflict_with_clearance(
    first: LayoutPlacement,
    second: LayoutPlacement,
    clearance: float,
) -> bool:
    if not _rectangles_overlap_with_clearance(first, second, clearance):
        return False
    if first.collision_points and second.collision_points:
        return _polygons_conflict_with_clearance(
            _absolute_collision_points(first),
            _absolute_collision_points(second),
            clearance,
        )
    return True


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


def _polygons_conflict_with_clearance(
    first: tuple[Point, ...],
    second: tuple[Point, ...],
    clearance: float,
) -> bool:
    if not _polygon_bounds_overlap_with_clearance(first, second, clearance):
        return False

    first_edges = _polygon_edges_with_bounds(first)
    second_edges = _polygon_edges_with_bounds(second)
    for first_start, first_end, first_bounds in first_edges:
        for second_start, second_end, second_bounds in second_edges:
            if _bounds_overlap(first_bounds, second_bounds) and _segments_intersect(
                first_start,
                first_end,
                second_start,
                second_end,
            ):
                return True

    if _point_in_polygon(first[0], second) or _point_in_polygon(second[0], first):
        return True
    if clearance <= EPSILON:
        return False

    for first_start, first_end, first_bounds in first_edges:
        for second_start, second_end, second_bounds in second_edges:
            if not _bounds_overlap_with_clearance(first_bounds, second_bounds, clearance):
                continue
            if _segment_distance_without_intersection(first_start, first_end, second_start, second_end) + EPSILON < clearance:
                return True
    return False


def _polygon_bounds_overlap_with_clearance(
    first: tuple[Point, ...],
    second: tuple[Point, ...],
    clearance: float,
) -> bool:
    first_min_x, first_min_y, first_max_x, first_max_y = _point_bounds(first)
    second_min_x, second_min_y, second_max_x, second_max_y = _point_bounds(second)
    separated = (
        first_max_x + clearance <= second_min_x + EPSILON
        or second_max_x + clearance <= first_min_x + EPSILON
        or first_max_y + clearance <= second_min_y + EPSILON
        or second_max_y + clearance <= first_min_y + EPSILON
    )
    return not separated


def _point_bounds(points: tuple[Point, ...]) -> tuple[float, float, float, float]:
    xs = tuple(point[0] for point in points)
    ys = tuple(point[1] for point in points)
    return min(xs), min(ys), max(xs), max(ys)


def _polygons_touch_or_overlap(first: tuple[Point, ...], second: tuple[Point, ...]) -> bool:
    for first_start, first_end in _polygon_edges(first):
        for second_start, second_end in _polygon_edges(second):
            if _segments_intersect(first_start, first_end, second_start, second_end):
                return True

    return _point_in_polygon(first[0], second) or _point_in_polygon(second[0], first)


def _polygons_within_clearance(first: tuple[Point, ...], second: tuple[Point, ...], clearance: float) -> bool:
    for first_start, first_end in _polygon_edges(first):
        for second_start, second_end in _polygon_edges(second):
            if _segment_distance_without_intersection(first_start, first_end, second_start, second_end) + EPSILON < clearance:
                return True
    return False


def _polygon_edges(points: tuple[Point, ...]) -> tuple[tuple[Point, Point], ...]:
    if len(points) < 2:
        return ()
    return tuple((point, points[(index + 1) % len(points)]) for index, point in enumerate(points))


def _polygon_edges_with_bounds(
    points: tuple[Point, ...],
) -> tuple[tuple[Point, Point, tuple[float, float, float, float]], ...]:
    return tuple(
        (start, end, _segment_bounds(start, end))
        for start, end in _polygon_edges(points)
    )


def _segment_bounds(start: Point, end: Point) -> tuple[float, float, float, float]:
    return min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1])


def _bounds_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    first_min_x, first_min_y, first_max_x, first_max_y = first
    second_min_x, second_min_y, second_max_x, second_max_y = second
    separated = (
        first_max_x < second_min_x - EPSILON
        or second_max_x < first_min_x - EPSILON
        or first_max_y < second_min_y - EPSILON
        or second_max_y < first_min_y - EPSILON
    )
    return not separated


def _bounds_overlap_with_clearance(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
    clearance: float,
) -> bool:
    first_min_x, first_min_y, first_max_x, first_max_y = first
    second_min_x, second_min_y, second_max_x, second_max_y = second
    separated = (
        first_max_x + clearance <= second_min_x + EPSILON
        or second_max_x + clearance <= first_min_x + EPSILON
        or first_max_y + clearance <= second_min_y + EPSILON
        or second_max_y + clearance <= first_min_y + EPSILON
    )
    return not separated


def _segments_intersect(first_start: Point, first_end: Point, second_start: Point, second_end: Point) -> bool:
    first_cross_start = _cross(first_start, first_end, second_start)
    first_cross_end = _cross(first_start, first_end, second_end)
    second_cross_start = _cross(second_start, second_end, first_start)
    second_cross_end = _cross(second_start, second_end, first_end)

    if (
        first_cross_start > EPSILON
        and first_cross_end < -EPSILON
        or first_cross_start < -EPSILON
        and first_cross_end > EPSILON
    ) and (
        second_cross_start > EPSILON
        and second_cross_end < -EPSILON
        or second_cross_start < -EPSILON
        and second_cross_end > EPSILON
    ):
        return True

    return (
        abs(first_cross_start) <= EPSILON
        and _point_on_segment(second_start, first_start, first_end)
        or abs(first_cross_end) <= EPSILON
        and _point_on_segment(second_end, first_start, first_end)
        or abs(second_cross_start) <= EPSILON
        and _point_on_segment(first_start, second_start, second_end)
        or abs(second_cross_end) <= EPSILON
        and _point_on_segment(first_end, second_start, second_end)
    )


def _cross(start: Point, end: Point, point: Point) -> float:
    return (end[0] - start[0]) * (point[1] - start[1]) - (end[1] - start[1]) * (point[0] - start[0])


def _point_on_segment(point: Point, start: Point, end: Point) -> bool:
    return (
        min(start[0], end[0]) - EPSILON <= point[0] <= max(start[0], end[0]) + EPSILON
        and min(start[1], end[1]) - EPSILON <= point[1] <= max(start[1], end[1]) + EPSILON
    )


def _point_in_polygon(point: Point, polygon: tuple[Point, ...]) -> bool:
    inside = False
    for start, end in _polygon_edges(polygon):
        if abs(_cross(start, end, point)) <= EPSILON and _point_on_segment(point, start, end):
            return True
        if (start[1] > point[1]) == (end[1] > point[1]):
            continue
        crossing_x = (end[0] - start[0]) * (point[1] - start[1]) / (end[1] - start[1]) + start[0]
        if point[0] < crossing_x:
            inside = not inside
    return inside


def _segment_distance_without_intersection(
    first_start: Point,
    first_end: Point,
    second_start: Point,
    second_end: Point,
) -> float:
    return min(
        _point_segment_distance(first_start, second_start, second_end),
        _point_segment_distance(first_end, second_start, second_end),
        _point_segment_distance(second_start, first_start, first_end),
        _point_segment_distance(second_end, first_start, first_end),
    )


def _point_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= EPSILON:
        return hypot(point[0] - start[0], point[1] - start[1])

    ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
    clamped = min(1.0, max(0.0, ratio))
    projection = (start[0] + clamped * dx, start[1] + clamped * dy)
    return hypot(point[0] - projection[0], point[1] - projection[1])


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
    seen: set[tuple[tuple[str, float, float, float, float, int], ...]] = set()
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
    seen: set[tuple[str, float, float, float, float, int]] = set()
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
) -> tuple[tuple[str, float, float, float, float, int], ...]:
    return tuple(_placement_geometry_key(placement) for placement in placements)


def _placement_geometry_key(placement: LayoutPlacement) -> tuple[str, float, float, float, float, int]:
    return (
        placement.piece_id,
        round(placement.x, COORDINATE_KEY_PRECISION),
        round(placement.y, COORDINATE_KEY_PRECISION),
        round(placement.width, COORDINATE_KEY_PRECISION),
        round(placement.height, COORDINATE_KEY_PRECISION),
        placement.rotation_degrees,
    )


def _bounded_coordinates(values: set[float], upper_bound: float | None, *, limit: int | None = None) -> tuple[float, ...]:
    bounded: set[float] = set()
    for value in values:
        if value < -EPSILON:
            continue
        if upper_bound is not None and value > upper_bound + EPSILON:
            continue
        bounded.add(_clean_coordinate(value))
    ordered = tuple(sorted(bounded))
    if limit is None or len(ordered) <= limit:
        return ordered
    low_count = limit // 2
    high_count = limit - low_count
    return tuple(sorted({*ordered[:low_count], *ordered[-high_count:]}))


def _oriented_outline_points(metric: PieceMetrics, rotation_degrees: int) -> tuple[Point, ...]:
    if not metric.points:
        return ()

    width = metric.bbox.width
    height = metric.bbox.height
    local_points = tuple(
        (
            _clean_coordinate(point[0] - metric.bbox.min_x),
            _clean_coordinate(metric.bbox.max_y - point[1]),
        )
        for point in metric.points
    )
    return tuple(_rotate_outline_point(point, width, height, rotation_degrees) for point in local_points)


def _rotate_outline_point(point: Point, width: float, height: float, rotation_degrees: int) -> Point:
    x, y = point
    if rotation_degrees == 90:
        return _clean_coordinate(height - y), _clean_coordinate(x)
    if rotation_degrees == 180:
        return _clean_coordinate(width - x), _clean_coordinate(height - y)
    if rotation_degrees == 270:
        return _clean_coordinate(y), _clean_coordinate(width - x)
    return _clean_coordinate(x), _clean_coordinate(y)


def _absolute_outline_points(placement: LayoutPlacement) -> tuple[Point, ...]:
    return tuple(
        (
            _clean_coordinate(placement.x + point[0]),
            _clean_coordinate(placement.y + point[1]),
        )
        for point in placement.outline_points
    )


def _absolute_collision_points(placement: LayoutPlacement) -> tuple[Point, ...]:
    return tuple(
        (
            _clean_coordinate(placement.x + point[0]),
            _clean_coordinate(placement.y + point[1]),
        )
        for point in placement.collision_points
    )


def _downsample_outline_points(points: tuple[Point, ...], max_points: int) -> tuple[Point, ...]:
    if len(points) <= max_points or max_points <= 0:
        return points

    indexes = {int(index * len(points) / max_points) for index in range(max_points)}
    min_x_index = min(range(len(points)), key=lambda index: points[index][0])
    max_x_index = max(range(len(points)), key=lambda index: points[index][0])
    min_y_index = min(range(len(points)), key=lambda index: points[index][1])
    max_y_index = max(range(len(points)), key=lambda index: points[index][1])
    indexes.update((min_x_index, max_x_index, min_y_index, max_y_index))
    return tuple(point for index, point in enumerate(points) if index in indexes)


def _marker_length(placements: Sequence[LayoutPlacement]) -> float:
    return max((placement.bottom for placement in placements), default=0.0)


def _clean_coordinate(value: float) -> float:
    return 0.0 if abs(value) <= EPSILON else value


def _oriented_dimensions(metric: PieceMetrics, rotation_degrees: int) -> tuple[float, float]:
    if rotation_degrees in (90, 270):
        return metric.bbox.height, metric.bbox.width
    return metric.bbox.width, metric.bbox.height


def _select_bbox_orientation(
    metric: PieceMetrics,
    rotations: tuple[int, ...],
    fabric_width: float,
    row_x: float,
    clearance: float,
) -> int | None:
    placement_x = _next_shelf_x(row_x, clearance)
    for rotation in rotations:
        width, _height = _oriented_dimensions(metric, rotation)
        if placement_x + width <= fabric_width + EPSILON:
            return rotation
    return None


def _next_shelf_x(row_x: float, clearance: float) -> float:
    if row_x <= EPSILON:
        return 0.0
    return row_x + clearance


def _find_overlaps(placements: Sequence[LayoutPlacement], clearance: float = 0.0) -> tuple[LayoutOverlap, ...]:
    overlaps: list[LayoutOverlap] = []
    for first_index, first in enumerate(placements):
        for second in placements[first_index + 1 :]:
            if _placements_conflict_for_validation(first, second, clearance):
                overlaps.append(LayoutOverlap(first_piece_id=first.piece_id, second_piece_id=second.piece_id))
    return tuple(overlaps)


def _placements_conflict_for_validation(
    first: LayoutPlacement,
    second: LayoutPlacement,
    clearance: float,
) -> bool:
    if first.outline_points and second.outline_points:
        if not _rectangles_overlap_with_clearance(first, second, clearance):
            return False
        return _polygons_conflict_with_clearance(
            _absolute_outline_points(first),
            _absolute_outline_points(second),
            clearance,
        )
    if clearance > EPSILON:
        return _rectangles_overlap_with_clearance(first, second, clearance)
    return _rectangles_overlap(first, second)


def _rectangles_overlap(first: LayoutPlacement, second: LayoutPlacement) -> bool:
    separated = (
        first.right <= second.x + EPSILON
        or second.right <= first.x + EPSILON
        or first.bottom <= second.y + EPSILON
        or second.bottom <= first.y + EPSILON
    )
    return not separated
