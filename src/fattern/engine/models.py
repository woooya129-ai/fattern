"""Shared engine output models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fattern.geometry import BoundingBox, Point

Severity = Literal["info", "warning", "blocker"]


@dataclass(frozen=True)
class EngineMessage:
    code: str
    message: str
    severity: Severity


@dataclass(frozen=True)
class EntitySummary:
    total_entities: int
    counts_by_type: dict[str, int]
    lwpolyline_count: int
    closed_lwpolyline_count: int
    open_lwpolyline_count: int
    unsupported_entity_types: tuple[str, ...] = ()
    polyline_count: int = 0
    closed_polyline_count: int = 0
    open_polyline_count: int = 0


@dataclass(frozen=True)
class PolylineCandidate:
    piece_id: str
    layer: str
    points: tuple[Point, ...]
    closed: bool
    source_entity_index: int
    vertex_count: int | None = None
    piece_name: str | None = None
    size: str | None = None
    has_grainline: bool = False
    grainline_confidence: float | None = None
    grainline_layer: str | None = None
    grainline_start: Point | None = None
    grainline_end: Point | None = None


@dataclass(frozen=True)
class DxfLineEntity:
    layer: str
    start: Point
    end: Point
    source_entity_index: int


@dataclass(frozen=True)
class DxfTextEntity:
    layer: str
    text: str
    insert: Point
    source_entity_index: int


@dataclass(frozen=True)
class ExcludedCandidate:
    entity_type: str
    layer: str | None
    reason_code: str
    message: str
    source_entity_index: int


@dataclass(frozen=True)
class DxfParseResult:
    acad_version: str | None
    summary: EntitySummary
    piece_candidates: tuple[PolylineCandidate, ...]
    excluded_candidates: tuple[ExcludedCandidate, ...]
    messages: tuple[EngineMessage, ...]
    line_entities: tuple[DxfLineEntity, ...] = ()
    text_entities: tuple[DxfTextEntity, ...] = ()

    def has_blocker(self) -> bool:
        return any(message.severity == "blocker" for message in self.messages)


@dataclass(frozen=True)
class PieceMetrics:
    piece_id: str
    layer: str
    bbox: BoundingBox
    area: float
    perimeter: float
    unit: str
    point_count: int
    points: tuple[Point, ...] = ()
    seam_allowance_width: float = 0.0
    source_unit: str | None = None
    unit_scale: float = 1.0
    piece_name: str | None = None
    size: str | None = None
    has_grainline: bool = False


@dataclass(frozen=True)
class MetricsResult:
    metrics: tuple[PieceMetrics, ...]
    messages: tuple[EngineMessage, ...]
    source_unit: str | None = None
    unit_scale: float = 1.0

    def has_blocker(self) -> bool:
        return any(message.severity == "blocker" for message in self.messages)


@dataclass(frozen=True)
class LayoutPlacement:
    piece_id: str
    layer: str
    x: float
    y: float
    width: float
    height: float
    rotation_degrees: int
    outline_points: tuple[Point, ...] = ()
    collision_points: tuple[Point, ...] = ()

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class LayoutOverlap:
    first_piece_id: str
    second_piece_id: str


@dataclass(frozen=True)
class LayoutValidity:
    within_fabric_width: bool
    no_overlap: bool
    overlaps: tuple[LayoutOverlap, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.within_fabric_width and self.no_overlap


@dataclass(frozen=True)
class LayoutResult:
    placements: tuple[LayoutPlacement, ...]
    fabric_width: float
    marker_length: float
    efficiency: float
    clearance: float
    unit: str
    no_overlap: bool
    messages: tuple[EngineMessage, ...]
    within_fabric_width: bool = True
    overlaps: tuple[LayoutOverlap, ...] = ()
    total_piece_area: float = 0.0
    rotation_allowed_degrees: tuple[int, ...] = ()
    grainline_status: str = "unknown"
    one_way_fabric: bool | None = None

    def has_blocker(self) -> bool:
        return any(message.severity == "blocker" for message in self.messages)

    @property
    def validity(self) -> LayoutValidity:
        return LayoutValidity(
            within_fabric_width=self.within_fabric_width,
            no_overlap=self.no_overlap,
            overlaps=self.overlaps,
        )
