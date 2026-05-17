"""Engine entry points for DXF parsing, metrics, and layout."""

from .dxf import parse_dxf_file, parse_dxf_text
from .layout import estimate_bbox_shelf_layout, estimate_marker_layout, validate_marker_layout, validate_no_overlap
from .metrics import calculate_piece_metrics, calculate_piece_set_metrics
from .models import (
    DxfParseResult,
    EngineMessage,
    EntitySummary,
    ExcludedCandidate,
    LayoutOverlap,
    LayoutPlacement,
    LayoutResult,
    LayoutValidity,
    MetricsResult,
    PieceMetrics,
    PolylineCandidate,
)

__all__ = [
    "DxfParseResult",
    "EngineMessage",
    "EntitySummary",
    "ExcludedCandidate",
    "LayoutOverlap",
    "LayoutPlacement",
    "LayoutResult",
    "LayoutValidity",
    "MetricsResult",
    "PieceMetrics",
    "PolylineCandidate",
    "calculate_piece_metrics",
    "calculate_piece_set_metrics",
    "estimate_bbox_shelf_layout",
    "estimate_marker_layout",
    "parse_dxf_file",
    "parse_dxf_text",
    "validate_marker_layout",
    "validate_no_overlap",
]
