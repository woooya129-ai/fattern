"""Minimal DXF parser for closed apparel outline input."""

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
    "AC1009",
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
    children: tuple["_DxfEntity", ...] = ()


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
        polyline_count=0,
        closed_polyline_count=0,
        open_polyline_count=0,
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
    entity_pairs: list[tuple[int, str]] = []
    block_pairs_by_name: dict[str, list[tuple[int, str]]] = {}
    in_entities_section = False
    in_blocks_section = False
    pending_section = False
    in_block = False
    current_block_name: str | None = None
    current_block_pairs: list[tuple[int, str]] = []

    def commit_block() -> None:
        nonlocal in_block, current_block_name, current_block_pairs
        if in_block and current_block_name:
            block_pairs_by_name[current_block_name] = list(current_block_pairs)
        in_block = False
        current_block_name = None
        current_block_pairs = []

    for code, value in pairs:
        upper_value = value.upper()

        if code == 0 and upper_value == "SECTION":
            commit_block()
            pending_section = True
            in_entities_section = False
            in_blocks_section = False
            continue

        if pending_section and code == 2:
            in_entities_section = upper_value == "ENTITIES"
            in_blocks_section = upper_value == "BLOCKS"
            pending_section = False
            continue

        if code == 0 and upper_value in {"ENDSEC", "EOF"}:
            commit_block()
            in_entities_section = False
            in_blocks_section = False
            pending_section = False
            continue

        if in_entities_section:
            entity_pairs.append((code, value))
            continue

        if not in_blocks_section:
            continue

        if code == 0 and upper_value == "BLOCK":
            commit_block()
            in_block = True
            current_block_pairs = []
            continue

        if code == 0 and upper_value == "ENDBLK":
            commit_block()
            continue

        if in_block:
            if code == 2 and current_block_name is None:
                current_block_name = value
            current_block_pairs.append((code, value))

    commit_block()

    blocks = {
        name: _collect_entity_stream(tuple(block_pairs))
        for name, block_pairs in block_pairs_by_name.items()
    }
    return _expand_insert_entities(_collect_entity_stream(tuple(entity_pairs)), blocks)


def _collect_entity_stream(pairs: tuple[tuple[int, str], ...]) -> tuple[_DxfEntity, ...]:
    entities: list[_DxfEntity] = []
    current_type: str | None = None
    current_pairs: list[tuple[int, str]] = []
    current_children: list[_DxfEntity] = []
    in_polyline = False
    current_vertex_pairs: list[tuple[int, str]] | None = None

    def commit_current() -> None:
        nonlocal current_type, current_pairs, current_children, in_polyline, current_vertex_pairs
        if current_vertex_pairs is not None:
            current_children.append(_DxfEntity("VERTEX", tuple(current_vertex_pairs)))
            current_vertex_pairs = None
        if current_type is not None:
            entities.append(_DxfEntity(current_type, tuple(current_pairs), tuple(current_children)))
            current_type = None
            current_pairs = []
            current_children = []
            in_polyline = False

    for code, value in pairs:
        upper_value = value.upper()

        if code == 0 and upper_value in {"ENDSEC", "EOF", "ENDBLK"}:
            commit_current()
            continue

        if code == 0 and in_polyline:
            if upper_value == "VERTEX":
                if current_vertex_pairs is not None:
                    current_children.append(_DxfEntity("VERTEX", tuple(current_vertex_pairs)))
                current_vertex_pairs = []
                continue
            if upper_value == "SEQEND":
                commit_current()
                continue

            commit_current()
            current_type = upper_value
            current_pairs = []
            in_polyline = upper_value == "POLYLINE"
            continue

        if code == 0:
            commit_current()
            current_type = upper_value
            current_pairs = []
            current_children = []
            in_polyline = upper_value == "POLYLINE"
            continue

        if current_vertex_pairs is not None:
            current_vertex_pairs.append((code, value))
        elif current_type is not None:
            current_pairs.append((code, value))

    commit_current()
    return tuple(entities)


def _expand_insert_entities(
    entities: tuple[_DxfEntity, ...],
    blocks: dict[str, tuple[_DxfEntity, ...]],
) -> tuple[_DxfEntity, ...]:
    expanded: list[_DxfEntity] = []
    for entity in entities:
        if entity.entity_type != "INSERT":
            expanded.append(entity)
            continue

        block_name = _block_name_from_pairs(entity.pairs)
        block_entities = blocks.get(block_name or "")
        if block_entities is None:
            expanded.append(entity)
            continue

        dx, dy = _insert_offset(entity.pairs)
        expanded.extend(_translate_entity(item, dx, dy) for item in block_entities)
    return tuple(expanded)


def _block_name_from_pairs(pairs: tuple[tuple[int, str], ...]) -> str | None:
    for code, value in pairs:
        if code == 2:
            return value
    return None


def _insert_offset(pairs: tuple[tuple[int, str], ...]) -> tuple[float, float]:
    x = 0.0
    y = 0.0
    for code, value in pairs:
        if code == 10:
            x = _parse_float(value, 0, code)
        elif code == 20:
            y = _parse_float(value, 0, code)
    return x, y


def _translate_entity(entity: _DxfEntity, dx: float, dy: float) -> _DxfEntity:
    if dx == 0 and dy == 0:
        return entity
    return _DxfEntity(
        entity_type=entity.entity_type,
        pairs=_translate_pairs(entity.pairs, dx, dy),
        children=tuple(_translate_entity(child, dx, dy) for child in entity.children),
    )


def _translate_pairs(pairs: tuple[tuple[int, str], ...], dx: float, dy: float) -> tuple[tuple[int, str], ...]:
    translated: list[tuple[int, str]] = []
    for code, value in pairs:
        if code == 10:
            translated.append((code, _format_dxf_float(_parse_float(value, 0, code) + dx)))
        elif code == 20:
            translated.append((code, _format_dxf_float(_parse_float(value, 0, code) + dy)))
        else:
            translated.append((code, value))
    return tuple(translated)


def _format_dxf_float(value: float) -> str:
    return f"{value:.12g}"


def _summarize_entities(
    entities: tuple[_DxfEntity, ...],
) -> tuple[EntitySummary, list[PolylineCandidate], list[ExcludedCandidate], list[EngineMessage]]:
    counts_by_type: dict[str, int] = {}
    candidates: list[PolylineCandidate] = []
    excluded: list[ExcludedCandidate] = []
    messages: list[EngineMessage] = []
    closed_count = 0
    open_count = 0
    closed_polyline_count = 0
    open_polyline_count = 0

    for source_index, entity in enumerate(entities, start=1):
        counts_by_type[entity.entity_type] = counts_by_type.get(entity.entity_type, 0) + 1

        if entity.entity_type == "LWPOLYLINE":
            parsed = _parse_lwpolyline(entity, source_index, len(candidates) + 1)
        elif entity.entity_type == "POLYLINE":
            parsed = _parse_polyline(entity, source_index, len(candidates) + 1)
        else:
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

        messages.extend(parsed.messages)
        if parsed.candidate is not None:
            if entity.entity_type == "LWPOLYLINE":
                closed_count += 1
            else:
                closed_polyline_count += 1
            candidates.append(parsed.candidate)
        elif parsed.excluded is not None:
            if entity.entity_type == "LWPOLYLINE":
                open_count += 1
            else:
                open_polyline_count += 1
            excluded.append(parsed.excluded)

    supported_types = {"LWPOLYLINE", "POLYLINE"}
    unsupported_types = tuple(sorted(entity_type for entity_type in counts_by_type if entity_type not in supported_types))
    summary = EntitySummary(
        total_entities=len(entities),
        counts_by_type=counts_by_type,
        lwpolyline_count=counts_by_type.get("LWPOLYLINE", 0),
        closed_lwpolyline_count=closed_count,
        open_lwpolyline_count=open_count,
        polyline_count=counts_by_type.get("POLYLINE", 0),
        closed_polyline_count=closed_polyline_count,
        open_polyline_count=open_polyline_count,
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


def _parse_polyline(entity: _DxfEntity, source_index: int, piece_number: int) -> _ParsedPolyline:
    layer = _layer_from_pairs(entity.pairs) or "0"
    flags = 0
    points: list[Point] = []

    for code, value in entity.pairs:
        if code == 8:
            layer = value
        elif code == 70:
            flags = _parse_int(value, source_index, code)

    for child in entity.children:
        if child.entity_type != "VERTEX":
            continue
        x: float | None = None
        y: float | None = None
        for code, value in child.pairs:
            if code == 8 and layer == "0":
                layer = value
            elif code == 10:
                x = _parse_float(value, source_index, code)
            elif code == 20:
                y = _parse_float(value, source_index, code)
        if x is not None and y is not None:
            points.append((x, y))

    closed = bool(flags & 1) or (len(points) > 1 and points_equal(points[0], points[-1]))
    if not closed:
        message = f"POLYLINE entity {source_index} is not closed and was excluded."
        return _ParsedPolyline(
            candidate=None,
            excluded=ExcludedCandidate(
                entity_type="POLYLINE",
                layer=layer,
                reason_code="NON_CLOSED_CONTOUR",
                message=message,
                source_entity_index=source_index,
            ),
            messages=(EngineMessage(code="NON_CLOSED_CONTOUR", message=message, severity="warning"),),
        )

    return _ParsedPolyline(
        candidate=PolylineCandidate(
            piece_id=f"piece_{piece_number:04d}",
            layer=layer,
            points=normalize_ring(points),
            closed=True,
            source_entity_index=source_index,
            vertex_count=len(points),
        ),
        excluded=None,
        messages=(),
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
