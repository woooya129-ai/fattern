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


def calculate_piece_metrics(piece: PolylineCandidate, unit: str = DEFAULT_UNIT) -> MetricsResult:
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

    return MetricsResult(
        metrics=(
            PieceMetrics(
                piece_id=piece.piece_id,
                layer=piece.layer,
                bbox=bounding_box(points),
                area=polygon_area(points),
                perimeter=polygon_perimeter(points),
                unit=unit,
                point_count=len(points),
            ),
        ),
        messages=(),
    )


def calculate_piece_set_metrics(
    pieces: list[PolylineCandidate] | tuple[PolylineCandidate, ...],
    unit: str = DEFAULT_UNIT,
) -> MetricsResult:
    all_metrics: list[PieceMetrics] = []
    all_messages: list[EngineMessage] = []

    for piece in pieces:
        result = calculate_piece_metrics(piece, unit=unit)
        if result.has_blocker():
            return MetricsResult(metrics=(), messages=result.messages)
        all_metrics.extend(result.metrics)
        all_messages.extend(result.messages)

    return MetricsResult(metrics=tuple(all_metrics), messages=tuple(all_messages))
