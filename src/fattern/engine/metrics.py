"""Piece metrics built on deterministic geometry functions."""

from __future__ import annotations

from fattern.geometry import (
    Point,
    PolygonValidationError,
    bounding_box,
    polygon_area,
    polygon_perimeter,
    validate_simple_polygon,
)
from fattern.schemas import DEFAULT_UNIT

from .models import EngineMessage, MetricsResult, PieceMetrics, PolylineCandidate


DEFAULT_SEAM_ALLOWANCE_BY_UNIT = {
    "mm": 10.0,
    "cm": 1.0,
    "inch": 0.375,
}
CM_PER_UNIT = {
    "mm": 0.1,
    "cm": 1.0,
    "inch": 2.54,
}


def calculate_piece_metrics(
    piece: PolylineCandidate,
    unit: str = DEFAULT_UNIT,
    seam_allowance_width: float = 0.0,
    dxf_unit_hint: str = "auto",
    fabric_width: float | None = None,
    fabric_width_unit: str | None = None,
) -> MetricsResult:
    if seam_allowance_width < 0:
        return MetricsResult(
            metrics=(),
            messages=(
                EngineMessage(
                    code="INVALID_SEAM_ALLOWANCE",
                    message="Seam allowance width must be zero or greater.",
                    severity="blocker",
                ),
            ),
        )

    source_unit = _resolve_source_unit(
        (piece,),
        target_unit=unit,
        dxf_unit_hint=dxf_unit_hint,
        fabric_width=fabric_width,
        fabric_width_unit=fabric_width_unit,
    )
    unit_scale = _unit_scale(source_unit, unit)

    try:
        points = validate_simple_polygon(_scale_points(piece.points, unit_scale))
    except PolygonValidationError as exc:
        return MetricsResult(
            metrics=(),
            messages=(
                EngineMessage(
                    code=exc.code,
                    message=f"{piece.piece_id}: {exc}",
                    severity="blocker",
                ),
            ),
        )

    measured_points = _apply_seam_allowance(points, seam_allowance_width)
    messages = (
        *_autoscale_messages(source_unit, unit, unit_scale, dxf_unit_hint),
        *_seam_allowance_messages(piece.piece_id, seam_allowance_width, unit),
    )

    return MetricsResult(
        metrics=(
            PieceMetrics(
                piece_id=piece.piece_id,
                layer=piece.layer,
                bbox=bounding_box(measured_points),
                area=polygon_area(measured_points),
                perimeter=polygon_perimeter(measured_points),
                unit=unit,
                point_count=len(measured_points),
                points=measured_points,
                seam_allowance_width=seam_allowance_width,
                source_unit=source_unit,
                unit_scale=unit_scale,
            ),
        ),
        messages=messages,
        source_unit=source_unit,
        unit_scale=unit_scale,
    )


def calculate_piece_set_metrics(
    pieces: list[PolylineCandidate] | tuple[PolylineCandidate, ...],
    unit: str = DEFAULT_UNIT,
    seam_allowance_width: float = 0.0,
    dxf_unit_hint: str = "auto",
    fabric_width: float | None = None,
    fabric_width_unit: str | None = None,
) -> MetricsResult:
    all_metrics: list[PieceMetrics] = []
    pieces_tuple = tuple(pieces)
    source_unit = _resolve_source_unit(
        pieces_tuple,
        target_unit=unit,
        dxf_unit_hint=dxf_unit_hint,
        fabric_width=fabric_width,
        fabric_width_unit=fabric_width_unit,
    )
    unit_scale = _unit_scale(source_unit, unit)
    all_messages: list[EngineMessage] = list(_autoscale_messages(source_unit, unit, unit_scale, dxf_unit_hint))

    for piece in pieces_tuple:
        result = calculate_piece_metrics(
            piece,
            unit=unit,
            seam_allowance_width=seam_allowance_width,
            dxf_unit_hint=source_unit,
        )
        if result.has_blocker():
            return MetricsResult(
                metrics=(),
                messages=result.messages,
                source_unit=source_unit,
                unit_scale=unit_scale,
            )
        all_metrics.extend(result.metrics)
        all_messages.extend(
            message for message in result.messages if message.code not in {"DXF_UNIT_AUTOSCALE_APPLIED"}
        )

    return MetricsResult(
        metrics=tuple(all_metrics),
        messages=tuple(all_messages),
        source_unit=source_unit,
        unit_scale=unit_scale,
    )


def default_seam_allowance_width(unit: str = DEFAULT_UNIT) -> float:
    return DEFAULT_SEAM_ALLOWANCE_BY_UNIT.get(unit, DEFAULT_SEAM_ALLOWANCE_BY_UNIT[DEFAULT_UNIT])


def _scale_points(points: tuple[Point, ...], unit_scale: float) -> tuple[Point, ...]:
    if unit_scale == 1.0:
        return points
    return tuple((point[0] * unit_scale, point[1] * unit_scale) for point in points)


def _apply_seam_allowance(points: tuple[Point, ...], width: float) -> tuple[Point, ...]:
    if width <= 0:
        return points

    box = bounding_box(points)
    center_x = (box.min_x + box.max_x) / 2.0
    center_y = (box.min_y + box.max_y) / 2.0
    scale_x = (box.width + width * 2.0) / box.width
    scale_y = (box.height + width * 2.0) / box.height
    return tuple(
        (
            center_x + (point[0] - center_x) * scale_x,
            center_y + (point[1] - center_y) * scale_y,
        )
        for point in points
    )


def _resolve_source_unit(
    pieces: tuple[PolylineCandidate, ...],
    *,
    target_unit: str,
    dxf_unit_hint: str,
    fabric_width: float | None,
    fabric_width_unit: str | None,
) -> str:
    if dxf_unit_hint in CM_PER_UNIT:
        return dxf_unit_hint
    if dxf_unit_hint != "auto":
        return target_unit
    return _infer_apparel_dxf_unit(
        pieces,
        target_unit=target_unit,
        fabric_width=fabric_width,
        fabric_width_unit=fabric_width_unit,
    )


def _infer_apparel_dxf_unit(
    pieces: tuple[PolylineCandidate, ...],
    *,
    target_unit: str,
    fabric_width: float | None,
    fabric_width_unit: str | None,
) -> str:
    if not pieces:
        return target_unit

    max_dimension = 0.0
    max_width = 0.0
    for piece in pieces:
        try:
            box = bounding_box(piece.points)
        except PolygonValidationError:
            continue
        max_dimension = max(max_dimension, box.width, box.height)
        max_width = max(max_width, box.width)

    if max_dimension <= 0:
        return target_unit

    fabric_cm = _to_cm(fabric_width, fabric_width_unit or target_unit)
    best_unit = target_unit
    best_score = float("inf")
    for source_unit in ("mm", "cm", "inch"):
        major_cm = max_dimension * CM_PER_UNIT[source_unit]
        width_cm = max_width * CM_PER_UNIT[source_unit]
        score = _apparel_unit_score(major_cm, width_cm, fabric_cm)
        if source_unit == target_unit:
            score -= 0.25
        if score < best_score:
            best_unit = source_unit
            best_score = score
    return best_unit


def _apparel_unit_score(major_cm: float, width_cm: float, fabric_cm: float | None) -> float:
    score = 0.0
    if major_cm < 3.0:
        score += 80.0
    elif major_cm < 15.0:
        score += 12.0
    elif major_cm <= 180.0:
        score += 0.0
    elif major_cm <= 260.0:
        score += 8.0
    else:
        score += 60.0

    if fabric_cm is not None and fabric_cm > 0:
        if width_cm > fabric_cm * 1.2:
            score += 60.0
        elif width_cm > fabric_cm:
            score += 10.0
        elif width_cm < fabric_cm * 0.02:
            score += 10.0
    return score


def _to_cm(value: float | None, unit: str) -> float | None:
    if value is None or unit not in CM_PER_UNIT:
        return None
    return value * CM_PER_UNIT[unit]


def _unit_scale(source_unit: str, target_unit: str) -> float:
    if source_unit not in CM_PER_UNIT or target_unit not in CM_PER_UNIT:
        return 1.0
    return CM_PER_UNIT[source_unit] / CM_PER_UNIT[target_unit]


def _autoscale_messages(
    source_unit: str,
    target_unit: str,
    unit_scale: float,
    dxf_unit_hint: str,
) -> tuple[EngineMessage, ...]:
    if dxf_unit_hint != "auto" or source_unit == target_unit:
        return ()
    return (
        EngineMessage(
            code="DXF_UNIT_AUTOSCALE_APPLIED",
            message=f"DXF coordinate unit was inferred as {source_unit} and scaled to {target_unit} with factor {unit_scale:g}.",
            severity="warning",
        ),
    )


def _seam_allowance_messages(piece_id: str, width: float, unit: str) -> tuple[EngineMessage, ...]:
    if width <= 0:
        return ()
    return (
        EngineMessage(
            code="SEAM_ALLOWANCE_ESTIMATED",
            message=f"{piece_id}: average seam allowance {width:g} {unit} was applied to the piece outline.",
            severity="warning",
        ),
    )
