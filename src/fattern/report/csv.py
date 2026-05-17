"""CSV report rendering for marker layout results."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import StringIO

from fattern.engine import LayoutResult, PieceMetrics

CSV_FIELDS = (
    "piece_id",
    "piece_name",
    "size",
    "quantity",
    "area_mm2",
    "bbox_width_mm",
    "bbox_height_mm",
    "x_mm",
    "y_mm",
    "rotation",
    "grainline_status",
)


@dataclass(frozen=True)
class PieceReportMetadata:
    piece_name: str | None = None
    size: str | None = None
    quantity: int | None = None
    grainline_status: str | None = None


def render_marker_csv(
    result: LayoutResult,
    piece_metrics: Mapping[str, PieceMetrics] | None = None,
    piece_metadata: Mapping[str, PieceReportMetadata] | None = None,
) -> str:
    """Render placement rows as CSV.

    Fields missing from current engine output are emitted as empty values unless
    explicit metadata is supplied by the caller.
    """

    metrics_by_piece_id = piece_metrics or {}
    metadata_by_piece_id = piece_metadata or {}
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()

    for placement in result.placements:
        metrics = metrics_by_piece_id.get(placement.piece_id)
        metadata = metadata_by_piece_id.get(placement.piece_id)
        writer.writerow(
            {
                "piece_id": placement.piece_id,
                "piece_name": _text_or_empty(metadata.piece_name if metadata else None),
                "size": _text_or_empty(metadata.size if metadata else None),
                "quantity": _number_or_empty(metadata.quantity if metadata else None),
                "area_mm2": _number_or_empty(metrics.area if metrics else None),
                "bbox_width_mm": _number_or_empty(metrics.bbox.width if metrics else None),
                "bbox_height_mm": _number_or_empty(metrics.bbox.height if metrics else None),
                "x_mm": _number_or_empty(placement.x),
                "y_mm": _number_or_empty(placement.y),
                "rotation": _number_or_empty(placement.rotation_degrees),
                "grainline_status": _text_or_empty(
                    metadata.grainline_status if metadata and metadata.grainline_status is not None else None
                ),
            }
        )

    return buffer.getvalue()


def partial_csv_fields(resolved_fields: Sequence[str] = ()) -> Sequence[str]:
    """Return CSV fields that currently require external piece metadata."""

    resolved = set(resolved_fields)
    return tuple(
        field
        for field in ("piece_name", "size", "quantity", "grainline_status")
        if field not in resolved
    )


def _text_or_empty(value: str | None) -> str:
    return "" if value is None else value


def _number_or_empty(value: float | int | None) -> str:
    if value is None:
        return ""
    text = f"{value:.6f}" if isinstance(value, float) else str(value)
    return text.rstrip("0").rstrip(".") if "." in text else text
