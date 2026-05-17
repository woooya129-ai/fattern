"""ORCH-002 MCP tool-chain execution.

This module coordinates existing MCP tools and render/report helpers. It does
not parse DXF coordinates, calculate geometry values, or build SVG paths.
"""

from __future__ import annotations

import html
import re
from base64 import b64encode
from collections.abc import Iterable, Mapping
from typing import Any

from fattern.engine import EngineMessage, ExcludedCandidate, LayoutResult
from fattern.mcp import McpToolRegistry
from fattern.orchestration.intent import normalize_user_intent, validate_user_intent
from fattern.schemas import DEFAULT_CLEARANCE_CM, ID_PATTERN
from fattern.render import render_marker_svg
from fattern.report import render_marker_report

ToolResponse = dict[str, Any]

STOPPED_AT_VALUES = frozenset(
    {
        "completed",
        "adapt_marker_yield_request",
        "normalize_user_intent",
        "create_job",
        "register_input_file",
        "parse_dxf",
        "extract_pattern_pieces",
        "calculate_piece_metrics",
        "estimate_marker_layout",
        "render_marker_report",
    }
)

CHAIN_STEPS = (
    "create_job",
    "register_input_file",
    "parse_dxf",
    "extract_pattern_pieces",
    "calculate_piece_metrics",
    "estimate_marker_layout",
)

ADAPTER_STOPPED_AT = "adapt_marker_yield_request"

ADAPTER_UNSUPPORTED_FIELDS = (
    "size_ratio",
    "piece_quantity",
    "shrinkage",
    "fabric_type",
    "stretch_direction",
)

VALID_HIGH_LEVEL_ROTATIONS = {0, 90, 180, 270}
NON_ONE_WAY_NAP_DIRECTIONS = {"two_way", "none", "no_nap", "not_one_way"}

REPORT_NUMERIC_FIELDS = (
    "fabric_width",
    "marker_length",
    "efficiency",
    "total_piece_area",
    "clearance",
)

FORBIDDEN_CERTAINTY_PHRASES = (
    "확정 요척",
    "확정요척",
    "확정 수율",
    "확정수율",
    "보장 요척",
    "보장요척",
    "final yield",
    "guaranteed yield",
)


class ChainResultValidationError(ValueError):
    pass


class ReportValidationError(ValueError):
    pass


def execute_marker_estimation(
    user_intent: dict[str, Any],
    *,
    dxf_file_name: str,
    dxf_content: bytes | str,
    registry: McpToolRegistry | None = None,
    job_name: str = "fattern",
    user_note: str = "",
) -> dict[str, Any]:
    """Run the ORCH-002 marker estimation chain from normalized UserIntent."""

    validate_user_intent(user_intent)
    active_registry = registry or McpToolRegistry()
    missing_fields = list(user_intent.get("missing_fields", []))
    if missing_fields:
        return {
            "status": "needs_clarification",
            "stopped_at": "normalize_user_intent",
            "missing_fields": missing_fields,
            "tool_calls": [],
            "warnings": [],
            "errors": [],
        }

    state: dict[str, Any] = {
        "status": "running",
        "stopped_at": None,
        "tool_calls": [],
        "warnings": [],
        "errors": [],
    }

    create_response = _call_tool(
        active_registry,
        state,
        "create_job",
        {"schema_version": "1.0", "job_name": job_name, "user_note": user_note},
    )
    if _blocked(create_response):
        return _blocked_result(state, "create_job", create_response)

    job_id = create_response["job_id"]
    state["job_id"] = job_id

    data = dxf_content.encode("utf-8") if isinstance(dxf_content, str) else bytes(dxf_content)
    register_response = _call_tool(
        active_registry,
        state,
        "register_input_file",
        {
            "schema_version": "1.0",
            "job_id": job_id,
            "file_name": dxf_file_name,
            "content_base64": b64encode(data).decode("ascii"),
        },
    )
    if _blocked(register_response):
        return _blocked_result(state, "register_input_file", register_response)

    file_id = register_response["file_id"]

    parse_response = _call_tool(
        active_registry,
        state,
        "parse_dxf",
        {
            "schema_version": "1.0",
            "job_id": job_id,
            "file_id": file_id,
            "unit_hint": user_intent.get("dxf_unit_hint", "auto"),
        },
    )
    if _blocked(parse_response):
        return _blocked_result(state, "parse_dxf", parse_response)

    dxf_parse_id = parse_response["dxf_parse_id"]
    state["dxf_parse_id"] = dxf_parse_id

    extract_response = _call_tool(
        active_registry,
        state,
        "extract_pattern_pieces",
        {
            "schema_version": "1.0",
            "job_id": job_id,
            "dxf_parse_id": dxf_parse_id,
            "extraction_mode": "closed_polylines_only",
            "outline_layer_names": [],
            "grainline_layer_names": [],
        },
    )
    if _blocked(extract_response):
        return _blocked_result(state, "extract_pattern_pieces", extract_response)

    piece_set_id = extract_response["piece_set_id"]
    state["piece_set_id"] = piece_set_id

    metrics_response = _call_tool(
        active_registry,
        state,
        "calculate_piece_metrics",
        {
            "schema_version": "1.0",
            "job_id": job_id,
            "piece_set_id": piece_set_id,
            "unit": user_intent["unit"],
            "dxf_unit_hint": user_intent.get("dxf_unit_hint", "auto"),
            "fabric_width": user_intent["fabric"]["width"],
            "fabric_width_unit": user_intent["fabric"]["width_unit"],
            "seam_allowance_width": _seam_allowance_width(user_intent),
        },
    )
    if _blocked(metrics_response):
        return _blocked_result(state, "calculate_piece_metrics", metrics_response)

    metrics_id = metrics_response["metrics_id"]
    state["metrics_id"] = metrics_id
    state["dxf_unit"] = metrics_response.get("dxf_unit")
    state["unit_scale"] = metrics_response.get("unit_scale")

    layout_response = _call_tool(
        active_registry,
        state,
        "estimate_marker_layout",
        {
            "schema_version": "1.0",
            "job_id": job_id,
            "metrics_id": metrics_id,
            "fabric_width": user_intent["fabric"]["width"],
            "fabric_width_unit": user_intent["fabric"]["width_unit"],
            "rotation_allowed_degrees": list(user_intent["rules"]["rotation_allowed_degrees"]),
            "clearance": user_intent["rules"]["clearance"],
            "one_way_fabric": user_intent["rules"]["one_way_fabric"],
            "grainline_status": _grainline_status(extract_response, user_intent),
            "grainline_required": user_intent["rules"]["grainline_required"],
        },
    )
    if _blocked(layout_response):
        return _blocked_result(state, "estimate_marker_layout", layout_response)

    layout_id = layout_response["layout_id"]
    state["layout_id"] = layout_id
    state["layout"] = _public_layout(layout_response)

    layout_result = active_registry.store.get_layout(job_id, layout_id)
    parse_result = active_registry.store.get_dxf_parse(job_id, dxf_parse_id)

    svg_text = render_marker_svg(layout_result)
    svg_artifact_id = active_registry.store.register_artifact(
        job_id,
        "marker_preview.svg",
        svg_text,
        media_type="image/svg+xml",
    )

    report_text = render_marker_report(
        layout_result,
        warnings=_engine_warnings(state["warnings"]),
        excluded_pieces=parse_result.excluded_candidates,
    )
    try:
        validate_final_report(
            state,
            layout_result,
            report_text,
            excluded_piece_ids=_excluded_report_ids(parse_result.excluded_candidates),
        )
    except ReportValidationError as exc:
        return _local_blocker(state, "render_marker_report", "REPORT_VALIDATION_FAILED", str(exc))

    report_artifact_id = active_registry.store.register_artifact(
        job_id,
        "marker_report.md",
        report_text,
        media_type="text/markdown",
    )

    state.update(
        {
            "status": "completed",
            "stopped_at": "completed",
            "svg_artifact_id": svg_artifact_id,
            "report_artifact_id": report_artifact_id,
        }
    )
    return _finalize(state)


def adapt_marker_yield_request(request: Mapping[str, Any]) -> dict[str, Any]:
    """Convert the v0.4 high-level request shape into existing UserIntent.

    This adapter only maps fields already represented in UserIntent and the
    ORCH-002 tool chain. Fields that need schema or engine policy support are
    reported as blockers instead of being silently ignored.
    """

    if not isinstance(request, Mapping):
        return _adapter_blocker(
            [_message("INVALID_MARKER_YIELD_REQUEST", "High-level marker yield request must be an object.", "blocker")]
        )

    warnings: list[dict[str, Any]] = []
    errors = _high_level_request_blockers(request)
    if errors:
        return _adapter_blocker(errors, warnings)

    fabric_width = _selected_fabric_width(request, warnings)
    seam_allowance = _adapt_seam_allowance(request)
    raw_intent = {
        "file_id": request.get("pattern_file_id"),
        "unit": request.get("unit"),
        "fabric_width": fabric_width,
        "rules": {
            "grainline_required": _high_level_bool(request.get("grainline_required"), default=True),
            "seam_allowance_included": seam_allowance["included"],
            "seam_allowance_width": seam_allowance["width"],
            "one_way_fabric": _adapt_nap_direction(request.get("nap_direction"), warnings),
            "rotation_allowed_degrees": _adapt_allowed_rotation(request.get("allowed_rotation")),
            "clearance": _adapt_spacing(request.get("spacing"), warnings),
        },
    }
    intent = normalize_user_intent(raw_intent)
    return {
        "status": "ready",
        "stopped_at": None,
        "user_intent": intent,
        "warnings": warnings,
        "errors": [],
    }


def execute_marker_yield_request(
    request: Mapping[str, Any],
    *,
    dxf_file_name: str | None = None,
    dxf_content: bytes | str | None = None,
    registry: McpToolRegistry | None = None,
    job_name: str = "fattern",
    user_note: str = "",
) -> dict[str, Any]:
    """Run a high-level marker yield request through the existing chain when safe."""

    adapted = adapt_marker_yield_request(request)
    if adapted["status"] == "blocked":
        return adapted

    user_intent = adapted["user_intent"]
    missing_fields = list(user_intent.get("missing_fields", []))
    if missing_fields:
        return {
            "status": "needs_clarification",
            "stopped_at": "normalize_user_intent",
            "missing_fields": missing_fields,
            "tool_calls": [],
            "warnings": adapted["warnings"],
            "errors": [],
        }

    if dxf_file_name is None or dxf_content is None:
        return _adapter_blocker(
            [
                _message(
                    "PATTERN_FILE_MAPPING_UNRESOLVED",
                    "pattern_file_id cannot be resolved to an existing job/file mapping by the current orchestration contract.",
                    "blocker",
                )
            ],
            adapted["warnings"],
        )

    result = execute_marker_estimation(
        user_intent,
        dxf_file_name=dxf_file_name,
        dxf_content=dxf_content,
        registry=registry,
        job_name=job_name,
        user_note=user_note,
    )
    if adapted["warnings"]:
        merged_warnings = list(adapted["warnings"])
        _extend_unique_warnings(merged_warnings, result.get("warnings", []))
        result["warnings"] = merged_warnings
    return result


def validate_stopped_at(value: object) -> str:
    if not isinstance(value, str) or value not in STOPPED_AT_VALUES:
        raise ChainResultValidationError(f"Invalid stopped_at value: {value!r}")
    return value


def _high_level_request_blockers(request: Mapping[str, Any]) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []
    for field in ADAPTER_UNSUPPORTED_FIELDS:
        if field in request and request.get(field) not in (None, {}, []):
            blockers.append(
                _message(
                    f"{field.upper()}_UNSUPPORTED_BY_CHAIN",
                    f"{field} is not represented in the existing UserIntent or MCP tool-chain contract.",
                    "blocker",
                )
            )

    shrinkage = request.get("shrinkage_percent")
    if shrinkage not in (None, 0, 0.0):
        blockers.append(
            _message(
                "SHRINKAGE_UNSUPPORTED_BY_CHAIN",
                "shrinkage_percent has no existing UserIntent or MCP tool-chain mapping.",
                "blocker",
            )
        )

    pattern_file_id = request.get("pattern_file_id")
    if pattern_file_id is not None and (
        not isinstance(pattern_file_id, str)
        or not pattern_file_id.startswith("file_")
        or re.fullmatch(ID_PATTERN, pattern_file_id) is None
    ):
        blockers.append(_message("INVALID_PATTERN_FILE_ID", "pattern_file_id must be an opaque file id.", "blocker"))

    if _invalid_non_negative_number(request, "cuttable_width"):
        blockers.append(_message("INVALID_CUTTABLE_WIDTH", "cuttable_width must be a positive number.", "blocker"))
    if _invalid_non_negative_number(request, "fabric_width"):
        blockers.append(_message("INVALID_FABRIC_WIDTH", "fabric_width must be a positive number.", "blocker"))
    if _invalid_non_negative_number(request, "spacing", allow_zero=True):
        blockers.append(_message("INVALID_SPACING", "spacing must be zero or greater.", "blocker"))

    if _invalid_allowed_rotation(request.get("allowed_rotation")):
        blockers.append(
            _message(
                "INVALID_ALLOWED_ROTATION",
                "allowed_rotation must contain only 0, 90, 180, or 270.",
                "blocker",
            )
        )

    nap_direction = request.get("nap_direction")
    normalized_nap = _normalized_text(nap_direction)
    if nap_direction is not None and normalized_nap not in {"one_way", *NON_ONE_WAY_NAP_DIRECTIONS}:
        blockers.append(
            _message(
                "UNSUPPORTED_NAP_DIRECTION",
                "nap_direction cannot be safely mapped to one_way_fabric.",
                "blocker",
            )
        )

    seam_allowance = request.get("seam_allowance")
    if seam_allowance is not None:
        if not isinstance(seam_allowance, Mapping):
            blockers.append(_message("INVALID_SEAM_ALLOWANCE", "seam_allowance must be an object.", "blocker"))
        else:
            status = _normalized_text(seam_allowance.get("status"))
            if status not in {"included", "excluded", "unknown", ""}:
                blockers.append(
                    _message("INVALID_SEAM_ALLOWANCE_STATUS", "seam_allowance.status is not supported.", "blocker")
                )
            fallback_width = seam_allowance.get("fallback_width")
            if fallback_width is not None and (
                not isinstance(fallback_width, (int, float)) or isinstance(fallback_width, bool) or fallback_width < 0
            ):
                blockers.append(
                    _message(
                        "INVALID_SEAM_ALLOWANCE_WIDTH",
                        "seam_allowance.fallback_width must be zero or greater.",
                        "blocker",
                    )
                )

    return blockers


def _selected_fabric_width(request: Mapping[str, Any], warnings: list[dict[str, Any]]) -> Any:
    cuttable_width = request.get("cuttable_width")
    if cuttable_width is not None:
        warnings.append(
            _message(
                "CUTTABLE_WIDTH_USED",
                "cuttable_width was mapped to fabric.width because it has priority over fabric_width.",
                "warning",
            )
        )
        return cuttable_width
    return request.get("fabric_width")


def _adapt_spacing(value: Any, warnings: list[dict[str, Any]]) -> Any:
    if value is None:
        return DEFAULT_CLEARANCE_CM
    warnings.append(
        _message(
            "SPACING_MAPPED_TO_CLEARANCE",
            "spacing was mapped to rules.clearance because both represent minimum piece gap in the selected unit.",
            "warning",
        )
    )
    return value


def _adapt_allowed_rotation(value: Any) -> list[int]:
    if value is None:
        return [0]
    return [int(rotation) for rotation in value]


def _adapt_nap_direction(value: Any, warnings: list[dict[str, Any]]) -> bool | None:
    normalized = _normalized_text(value)
    if normalized == "one_way":
        warnings.append(
            _message(
                "NAP_DIRECTION_ONE_WAY_MAPPED",
                "nap_direction=one_way was mapped to rules.one_way_fabric=true.",
                "warning",
            )
        )
        return True
    if normalized in NON_ONE_WAY_NAP_DIRECTIONS:
        return False
    return None


def _adapt_seam_allowance(request: Mapping[str, Any]) -> dict[str, Any]:
    seam_allowance = request.get("seam_allowance")
    if not isinstance(seam_allowance, Mapping):
        return {"included": None, "width": None}
    status = _normalized_text(seam_allowance.get("status"))
    if status == "included":
        return {"included": True, "width": None}
    if status == "excluded":
        return {"included": False, "width": seam_allowance.get("fallback_width")}
    return {"included": None, "width": None}


def _high_level_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _invalid_non_negative_number(request: Mapping[str, Any], field: str, *, allow_zero: bool = False) -> bool:
    value = request.get(field)
    if value is None:
        return False
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return True
    return value < 0 if allow_zero else value < 1


def _invalid_allowed_rotation(value: Any) -> bool:
    if value is None:
        return False
    if not isinstance(value, list) or not value:
        return True
    return any(
        not isinstance(rotation, int) or isinstance(rotation, bool) or rotation not in VALID_HIGH_LEVEL_ROTATIONS
        for rotation in value
    )


def _normalized_text(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _adapter_blocker(errors: list[dict[str, str]], warnings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "status": "blocked",
        "stopped_at": ADAPTER_STOPPED_AT,
        "tool_calls": [],
        "warnings": list(warnings or []),
        "errors": errors,
    }


def _message(code: str, message: str, severity: str) -> dict[str, str]:
    return {"code": code, "message": message, "severity": severity}


def validate_final_report(
    chain_result: Mapping[str, Any],
    layout_result: LayoutResult,
    report_text: str,
    *,
    excluded_piece_ids: Iterable[str] = (),
) -> None:
    """Validate final Markdown report against ORCH tool outputs.

    The guard only compares values already present in the ORCH-002 chain result
    and LayoutResult. It does not calculate marker length, efficiency, area, or
    bbox dimensions.
    """

    stopped_at = chain_result.get("stopped_at")
    if stopped_at is not None:
        validate_stopped_at(stopped_at)

    _validate_layout_echo(chain_result, layout_result)
    _validate_report_language(report_text)
    _validate_report_layout_numbers(report_text, layout_result)
    _validate_report_placements(report_text, layout_result)
    _validate_report_excluded_piece_ids(report_text, set(excluded_piece_ids))


def _call_tool(
    registry: McpToolRegistry,
    state: dict[str, Any],
    name: str,
    arguments: dict[str, Any],
) -> ToolResponse:
    response = registry.call_tool(name, arguments)
    state["tool_calls"].append(name)
    _extend_unique_warnings(state["warnings"], response.get("warnings", []))
    return response


def _extend_unique_warnings(target: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> None:
    seen = {
        (
            warning.get("code"),
            warning.get("message"),
            warning.get("severity"),
        )
        for warning in target
    }
    for warning in warnings:
        key = (
            warning.get("code"),
            warning.get("message"),
            warning.get("severity"),
        )
        if key in seen:
            continue
        target.append(warning)
        seen.add(key)


def _blocked(response: ToolResponse) -> bool:
    return any(error.get("severity") == "blocker" for error in response.get("errors", []))


def _blocked_result(state: dict[str, Any], stopped_at: str, response: ToolResponse) -> dict[str, Any]:
    state["status"] = "blocked"
    state["stopped_at"] = stopped_at
    state["errors"] = list(response.get("errors", []))
    return _finalize(state)


def _local_blocker(state: dict[str, Any], stopped_at: str, code: str, message: str) -> dict[str, Any]:
    state["status"] = "blocked"
    state["stopped_at"] = stopped_at
    state["errors"] = [{"code": code, "message": message, "severity": "blocker"}]
    return _finalize(state)


def _finalize(state: dict[str, Any]) -> dict[str, Any]:
    result = {"status": state["status"]}
    for key, value in state.items():
        if key == "status" or value is None:
            continue
        result[key] = value
    if "stopped_at" in result:
        validate_stopped_at(result["stopped_at"])
    return result


def _grainline_status(extract_response: ToolResponse, user_intent: Mapping[str, Any]) -> str:
    rules = user_intent.get("rules", {})
    if isinstance(rules, Mapping):
        explicit = rules.get("grainline_status")
        if explicit in {"present", "missing"}:
            return str(explicit)
    pieces = extract_response.get("piece_summary", [])
    if pieces and all(piece.get("has_grainline") is True for piece in pieces):
        return "present"
    return "missing"


def _seam_allowance_width(user_intent: Mapping[str, Any]) -> float:
    rules = user_intent.get("rules", {})
    if not isinstance(rules, Mapping) or rules.get("seam_allowance_included") is not False:
        return 0.0
    width = rules.get("seam_allowance_width")
    if isinstance(width, (int, float)) and not isinstance(width, bool) and width >= 0:
        return float(width)
    return 0.0


def _engine_warnings(warnings: list[dict[str, Any]]) -> tuple[EngineMessage, ...]:
    messages: list[EngineMessage] = []
    for warning in warnings:
        if warning.get("severity") != "warning":
            continue
        code = str(warning.get("code", "WARNING"))
        message = str(warning.get("message", "Warning"))
        messages.append(EngineMessage(code=code, message=message, severity="warning"))
    return tuple(messages)


def _public_layout(response: ToolResponse) -> dict[str, Any]:
    return {
        "fabric_width": response["fabric_width"],
        "marker_length": response["marker_length"],
        "efficiency": response["efficiency"],
        "clearance": response["clearance"],
        "unit": response["unit"],
        "total_piece_area": response["total_piece_area"],
        "rotation_allowed_degrees": list(response["rotation_allowed_degrees"]),
        "grainline_status": response.get("grainline_status", "unknown"),
        "one_way_fabric": response.get("one_way_fabric"),
        "layout_summary": response["layout_summary"],
        "validity": response["validity"],
    }


def _validate_layout_echo(chain_result: Mapping[str, Any], layout_result: LayoutResult) -> None:
    layout = chain_result.get("layout")
    if layout is None:
        return
    if not isinstance(layout, Mapping):
        raise ReportValidationError("chain layout must be an object")

    expected = {
        "fabric_width": layout_result.fabric_width,
        "marker_length": layout_result.marker_length,
        "efficiency": layout_result.efficiency,
        "clearance": layout_result.clearance,
        "unit": layout_result.unit,
        "total_piece_area": layout_result.total_piece_area,
        "rotation_allowed_degrees": list(layout_result.rotation_allowed_degrees),
        "grainline_status": layout_result.grainline_status,
        "one_way_fabric": layout_result.one_way_fabric,
        "validity": {
            "within_fabric_width": layout_result.within_fabric_width,
            "no_overlap": layout_result.no_overlap,
            "overlaps": [
                {"first_piece_id": overlap.first_piece_id, "second_piece_id": overlap.second_piece_id}
                for overlap in layout_result.overlaps
            ],
        },
    }

    for field, expected_value in expected.items():
        if layout.get(field) != expected_value:
            raise ReportValidationError(f"layout.{field} does not match LayoutResult")

    expected_rows = [_placement_row(placement) for placement in layout_result.placements]
    if layout.get("layout_summary") != expected_rows:
        raise ReportValidationError("layout.layout_summary does not match LayoutResult placements")


def _validate_report_language(report_text: str) -> None:
    lowered = report_text.lower()
    for phrase in FORBIDDEN_CERTAINTY_PHRASES:
        if phrase.lower() in lowered:
            raise ReportValidationError(f"forbidden certainty phrase found: {phrase}")


def _validate_report_layout_numbers(report_text: str, layout_result: LayoutResult) -> None:
    report_fields = _report_bullet_numbers(report_text)
    expected = {
        "fabric_width": layout_result.fabric_width,
        "marker_length": layout_result.marker_length,
        "efficiency": layout_result.efficiency,
        "total_piece_area": layout_result.total_piece_area,
        "area": layout_result.total_piece_area,
        "clearance": layout_result.clearance,
    }
    missing = [field for field in REPORT_NUMERIC_FIELDS if field != "total_piece_area" and field not in report_fields]
    if "total_piece_area" not in report_fields and "area" not in report_fields:
        missing.append("total_piece_area/area")
    if missing:
        raise ReportValidationError(f"report is missing numeric fields: {', '.join(missing)}")

    for field, actual in report_fields.items():
        if field not in expected:
            continue
        expected_text = _format_report_number(expected[field])
        if actual != expected_text:
            raise ReportValidationError(f"report {field} does not match LayoutResult")


def _validate_report_placements(report_text: str, layout_result: LayoutResult) -> None:
    rows = _report_table_rows(report_text, "Placements")
    if not layout_result.placements:
        if rows:
            raise ReportValidationError("report contains placements not present in LayoutResult")
        return

    expected = {placement.piece_id: placement for placement in layout_result.placements}
    seen: set[str] = set()
    if len(rows) != len(layout_result.placements):
        raise ReportValidationError("report placement count does not match LayoutResult")

    for row in rows:
        if len(row) != 7:
            raise ReportValidationError("report placement row has unexpected columns")
        piece_id, layer, x, y, width, height, rotation = row
        placement = expected.get(piece_id)
        if placement is None:
            raise ReportValidationError(f"report contains piece_id outside LayoutResult: {piece_id}")
        if piece_id in seen:
            raise ReportValidationError(f"report contains duplicate piece_id: {piece_id}")
        seen.add(piece_id)

        expected_cells = (
            placement.layer,
            _format_report_number(placement.x),
            _format_report_number(placement.y),
            _format_report_number(placement.width),
            _format_report_number(placement.height),
            str(placement.rotation_degrees),
        )
        actual_cells = (layer, x, y, width, height, rotation)
        if actual_cells != expected_cells:
            raise ReportValidationError(f"report placement values do not match LayoutResult: {piece_id}")


def _validate_report_excluded_piece_ids(report_text: str, allowed_piece_ids: set[str]) -> None:
    rows = _report_table_rows(report_text, "Excluded Pieces")
    for row in rows:
        if not row:
            continue
        piece_id = row[0]
        if piece_id not in allowed_piece_ids:
            raise ReportValidationError(f"report contains excluded piece outside tool output: {piece_id}")


def _report_bullet_numbers(report_text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    pattern = re.compile(r"^- ([a-z_]+): ([+-]?(?:\d+(?:\.\d*)?|\.\d+))(?=\s|$)", re.MULTILINE)
    for match in pattern.finditer(report_text):
        fields[match.group(1)] = match.group(2)
    return fields


def _report_table_rows(report_text: str, section_title: str) -> list[list[str]]:
    section = _markdown_section(report_text, section_title)
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _split_markdown_table_row(stripped)
        if not cells or all(_is_table_separator(cell) for cell in cells):
            continue
        if cells[0] in {"piece_id", "layer"}:
            continue
        rows.append(cells)
    return rows


def _markdown_section(report_text: str, section_title: str) -> str:
    marker = f"## {section_title}"
    start = report_text.find(marker)
    if start < 0:
        return ""
    next_start = report_text.find("\n## ", start + len(marker))
    if next_start < 0:
        return report_text[start:]
    return report_text[start:next_start]


def _split_markdown_table_row(row: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in row.strip():
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    cells.append("".join(current).strip())

    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return [html.unescape(cell) for cell in cells]


def _is_table_separator(cell: str) -> bool:
    stripped = cell.strip()
    return stripped != "" and all(char in {"-", ":"} for char in stripped)


def _format_report_number(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"


def _placement_row(placement: Any) -> dict[str, Any]:
    return {
        "piece_id": placement.piece_id,
        "layer": placement.layer,
        "x": placement.x,
        "y": placement.y,
        "width": placement.width,
        "height": placement.height,
        "rotation_degrees": placement.rotation_degrees,
    }


def _excluded_report_ids(excluded: Iterable[ExcludedCandidate]) -> tuple[str, ...]:
    return tuple(f"entity_{item.source_entity_index:04d}" for item in excluded)
