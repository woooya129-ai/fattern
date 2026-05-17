"""Minimal DXF parser for closed LWPOLYLINE MVP input."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fattern.geometry import Point, normalize_ring, points_equal

from .models import (
    DxfParseResult,
    EngineMessage,
    EntitySummary,
    ExcludedCandidate,
    PolylineCandidate,
)

SUPPORTED_ACAD_VERSIONS = {
    "AC1012",
    "AC1014",
    "AC1015",
    "AC1018",
    "AC1021",
    "AC1024",
    "AC1027",
    "AC1032",
    "AC1036",
}


class DxfParseError(ValueError):
    pass


@dataclass(frozen=True)
class _DxfEntity:
    entity_type: str
    pairs: tuple[tuple[int, str], ...]


def parse_dxf_file(path: str | Path) -> DxfParseResult:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = Path(path).read_text(encoding="latin-1")
    except OSError as exc:
        return _blocked_parse_result(f"DXF file could not be read: {exc}")
    return parse_dxf_text(text)


def parse_dxf_text(text: str) -> DxfParseResult:
    if not text.strip():
        return _blocked_parse_result("DXF file is empty.")

    try:
        pairs = _read_group_pairs(text)
        acad_version = _find_acad_version(pairs)
        if acad_version is not None and acad_version not in SUPPORTED_ACAD_VERSIONS:
            return DxfParseResult(
                acad_version=acad_version,
                summary=_empty_summary(),
                piece_candidates=(),
                excluded_candidates=(),
                messages=(
                    EngineMessage(
                        code="UNSUPPORTED_DXF_VERSION",
                        message=f"DXF version {acad_version} is not supported by the MVP parser.",
                        severity="blocker",
                    ),
                ),
            )

        entities = _collect_entities(pairs)
        summary, candidates, excluded, messages = _summarize_entities(entities)
        return DxfParseResult(
            acad_version=acad_version,
            summary=summary,
            piece_candidates=tuple(candidates),
            excluded_candidates=tuple(excluded),
            messages=tuple(messages),
        )
    except DxfParseError as exc:
        return _blocked_parse_result(str(exc))


def _blocked_parse_result(message: str) -> DxfParseResult:
    return DxfParseResult(
        acad_version=None,
        summary=_empty_summary(),
        piece_candidates=(),
        excluded_candidates=(),
        messages=(EngineMessage(code="PARSE_FAILED", message=message, severity="blocker"),),
    )


def _empty_summary() -> EntitySummary:
    return EntitySummary(
        total_entities=0,
        counts_by_type={},
        lwpolyline_count=0,
        closed_lwpolyline_count=0,
        open_lwpolyline_count=0,
        unsupported_entity_types=(),
    )


def _read_group_pairs(text: str) -> tuple[tuple[int, str], ...]:
    lines = text.splitlines()
    if len(lines) % 2 != 0:
        raise DxfParseError("DXF group code/value pairs are incomplete.")

    pairs: list[tuple[int, str]] = []
    for index in range(0, len(lines), 2):
        code_text = lines[index].strip()
        try:
            code = int(code_text)
        except ValueError as exc:
            raise DxfParseError(f"Invalid DXF group code at line {index + 1}.") from exc
        pairs.append((code, lines[index + 1].strip()))

    if not any(code == 0 and value.upper() == "EOF" for code, value in pairs):
        raise DxfParseError("DXF EOF marker is missing.")

    return tuple(pairs)


def _find_acad_version(pairs: tuple[tuple[int, str], ...]) -> str | None:
    for index, (code, value) in enumerate(pairs):
        if code == 9 and value.upper() == "$ACADVER":
            if index + 1 < len(pairs) and pairs[index + 1][0] == 1:
                return pairs[index + 1][1].upper()
            raise DxfParseError("DXF $ACADVER header is malformed.")
    return None


def _collect_entities(pairs: tuple[tuple[int, str], ...]) -> tuple[_DxfEntity, ...]:
    entities: list[_DxfEntity] = []
    in_entities_section = False
    pending_section = False
    current_type: str | None = None
    current_pairs: list[tuple[int, str]] = []

    def commit_current() -> None:
        nonlocal current_type, current_pairs
        if current_type is not None:
            entities.append(_DxfEntity(current_type, tuple(current_pairs)))
            current_type = None
            current_pairs = []

    for code, value in pairs:
        upper_value = value.upper()

        if code == 0 and upper_value == "SECTION":
            commit_current()
            pending_section = True
            in_entities_section = False
            continue

        if pending_section and code == 2:
            in_entities_section = upper_value == "ENTITIES"
            pending_section = False
            continue

        if code == 0 and upper_value in {"ENDSEC", "EOF"}:
            commit_current()
            in_entities_section = False
            pending_section = False
            continue

        if not in_entities_section:
            continue

        if code == 0:
            commit_current()
            current_type = upper_value
            current_pairs = []
            continue

        if current_type is not None:
            current_pairs.append((code, value))

    commit_current()
    return tuple(entities)


def _summarize_entities(
    entities: tuple[_DxfEntity, ...],
) -> tuple[EntitySummary, list[PolylineCandidate], list[ExcludedCandidate], list[EngineMessage]]:
    counts_by_type: dict[str, int] = {}
    candidates: list[PolylineCandidate] = []
    excluded: list[ExcludedCandidate] = []
    messages: list[EngineMessage] = []
    closed_count = 0
    open_count = 0

    for source_index, entity in enumerate(entities, start=1):
        counts_by_type[entity.entity_type] = counts_by_type.get(entity.entity_type, 0) + 1

        if entity.entity_type != "LWPOLYLINE":
            excluded.append(
                ExcludedCandidate(
                    entity_type=entity.entity_type,
                    layer=_layer_from_pairs(entity.pairs),
                    reason_code="UNSUPPORTED_ENTITY",
                    message=f"{entity.entity_type} is outside the closed LWPOLYLINE MVP scope.",
                    source_entity_index=source_index,
                )
            )
            continue

        parsed = _parse_lwpolyline(entity, source_index, len(candidates) + 1)
        messages.extend(parsed.messages)
        if parsed.candidate is not None:
            closed_count += 1
            candidates.append(parsed.candidate)
        elif parsed.excluded is not None:
            open_count += 1
            excluded.append(parsed.excluded)

    unsupported_types = tuple(sorted(entity_type for entity_type in counts_by_type if entity_type != "LWPOLYLINE"))
    summary = EntitySummary(
        total_entities=len(entities),
        counts_by_type=counts_by_type,
        lwpolyline_count=counts_by_type.get("LWPOLYLINE", 0),
        closed_lwpolyline_count=closed_count,
        open_lwpolyline_count=open_count,
        unsupported_entity_types=unsupported_types,
    )
    return summary, candidates, excluded, messages


@dataclass(frozen=True)
class _ParsedPolyline:
    candidate: PolylineCandidate | None
    excluded: ExcludedCandidate | None
    messages: tuple[EngineMessage, ...]


def _parse_lwpolyline(entity: _DxfEntity, source_index: int, piece_number: int) -> _ParsedPolyline:
    layer = _layer_from_pairs(entity.pairs) or "0"
    flags = 0
    declared_vertex_count: int | None = None
    points: list[Point] = []
    pending_x: float | None = None

    for code, value in entity.pairs:
        if code == 8:
            layer = value
        elif code == 70:
            flags = _parse_int(value, source_index, code)
        elif code == 90:
            declared_vertex_count = _parse_int(value, source_index, code)
        elif code == 10:
            if pending_x is not None:
                raise DxfParseError(f"LWPOLYLINE entity {source_index} has an x coordinate without y.")
            pending_x = _parse_float(value, source_index, code)
        elif code == 20:
            if pending_x is None:
                continue
            points.append((pending_x, _parse_float(value, source_index, code)))
            pending_x = None

    if pending_x is not None:
        raise DxfParseError(f"LWPOLYLINE entity {source_index} has an x coordinate without y.")

    closed = bool(flags & 1) or (len(points) > 1 and points_equal(points[0], points[-1]))
    if not closed:
        message = f"LWPOLYLINE entity {source_index} is not closed and was excluded."
        return _ParsedPolyline(
            candidate=None,
            excluded=ExcludedCandidate(
                entity_type="LWPOLYLINE",
                layer=layer,
                reason_code="NON_CLOSED_CONTOUR",
                message=message,
                source_entity_index=source_index,
            ),
            messages=(EngineMessage(code="NON_CLOSED_CONTOUR", message=message, severity="warning"),),
        )

    normalized_points = normalize_ring(points)
    messages: list[EngineMessage] = []
    if declared_vertex_count is not None and declared_vertex_count != len(points):
        messages.append(
            EngineMessage(
                code="VERTEX_COUNT_MISMATCH",
                message=f"LWPOLYLINE entity {source_index} declares {declared_vertex_count} vertices but has {len(points)}.",
                severity="warning",
            )
        )

    return _ParsedPolyline(
        candidate=PolylineCandidate(
            piece_id=f"piece_{piece_number:04d}",
            layer=layer,
            points=normalized_points,
            closed=True,
            source_entity_index=source_index,
            vertex_count=declared_vertex_count,
        ),
        excluded=None,
        messages=tuple(messages),
    )


def _layer_from_pairs(pairs: tuple[tuple[int, str], ...]) -> str | None:
    for code, value in pairs:
        if code == 8:
            return value
    return None


def _parse_float(value: str, source_index: int, code: int) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise DxfParseError(f"Entity {source_index} has an invalid numeric value for group code {code}.") from exc


def _parse_int(value: str, source_index: int, code: int) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise DxfParseError(f"Entity {source_index} has an invalid integer value for group code {code}.") from exc
