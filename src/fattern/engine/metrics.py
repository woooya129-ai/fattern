"""Piece metrics built on deterministic geometry functions."""

from __future__ import annotations

from fattern.geometry import (
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


def calculate_piece_metrics(
    piece: PolylineCandidate,
    unit: str = DEFAULT_UNIT,
    seam_allowance_width: float = 0.0,
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

    try:
        points = validate_simple_polygon(piece.points)
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
    messages = _seam_allowance_messages(piece.piece_id, seam_allowance_width, unit)

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
            ),
        ),
        messages=messages,
    )


def calculate_piece_set_metrics(
    pieces: list[PolylineCandidate] | tuple[PolylineCandidate, ...],
    unit: str = DEFAULT_UNIT,
    seam_allowance_width: float = 0.0,
) -> MetricsResult:
    all_metrics: list[PieceMetrics] = []
    all_messages: list[EngineMessage] = []

    for piece in pieces:
        result = calculate_piece_metrics(piece, unit=unit, seam_allowance_width=seam_allowance_width)
        if result.has_blocker():
            return MetricsResult(metrics=(), messages=result.messages)
        all_metrics.extend(result.metrics)
        all_messages.extend(result.messages)

    return MetricsResult(metrics=tuple(all_metrics), messages=tuple(all_messages))


def default_seam_allowance_width(unit: str = DEFAULT_UNIT) -> float:
    return DEFAULT_SEAM_ALLOWANCE_BY_UNIT.get(unit, DEFAULT_SEAM_ALLOWANCE_BY_UNIT[DEFAULT_UNIT])


def _apply_seam_allowance(points: tuple[tuple[float, float], ...], width: float) -> tuple[tuple[float, float], ...]:
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
