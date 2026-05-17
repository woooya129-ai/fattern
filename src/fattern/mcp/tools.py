"""Tool registry and wrappers for Fattern MCP calls."""

from __future__ import annotations

import re
from base64 import b64decode
from binascii import Error as Base64DecodeError
from copy import deepcopy
from dataclasses import replace
from typing import Any, Callable

from fattern.engine import (
    EngineMessage,
    LayoutResult,
    MetricsResult,
    PieceMetrics,
    PolylineCandidate,
    estimate_marker_layout as run_estimate_marker_layout,
    parse_dxf_file,
)
from fattern.engine.metrics import calculate_piece_set_metrics
from fattern.jobs import JobError, JobStore, SecurityError
from fattern.render import render_marker_svg

from .schemas import TOOL_SCHEMAS, list_tool_definitions
from .validation import ToolValidationError, validate_input

ToolResponse = dict[str, Any]


class McpToolRegistry:
    def __init__(self, store: JobStore | None = None) -> None:
        self.store = store or JobStore()
        self._handlers: dict[str, Callable[[dict[str, Any]], ToolResponse]] = {
            "get_estimation_questionnaire": self._get_estimation_questionnaire,
            "create_job": self._create_job,
            "register_input_file": self._register_input_file,
            "parse_dxf": self._parse_dxf,
            "extract_pattern_pieces": self._extract_pattern_pieces,
            "calculate_piece_metrics": self._calculate_piece_metrics,
            "estimate_marker_layout": self._estimate_marker_layout,
            "render_marker_svg": self._render_marker_svg,
            "get_job_status": self._get_job_status,
            "export_artifacts": self._export_artifacts,
        }

    def list_tools(self) -> list[dict]:
        return list_tool_definitions()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResponse:
        handler = self._handlers.get(name)
        if handler is None:
            return _error_response("TOOL_NOT_FOUND", "Tool was not found.")

        try:
            validate_input(TOOL_SCHEMAS[name], arguments)
            return handler(deepcopy(arguments))
        except ToolValidationError:
            return _error_response("TOOL_VALIDATION_FAILED", "Tool input validation failed.")
        except (JobError, SecurityError) as exc:
            code = "FILE_ACCESS_BLOCKED" if exc.code == "PATH_CONTAINMENT_FAILED" else exc.code
            return _error_response(code, exc.public_message)
        except Exception:
            return _error_response("INTERNAL_TOOL_ERROR", "Tool execution failed.")

    def _get_estimation_questionnaire(self, arguments: dict[str, Any]) -> ToolResponse:
        from fattern.orchestration.fabric_presets import FABRIC_WIDTH_PRESETS
        from fattern.orchestration.intent import build_estimation_questionnaire

        questionnaire = build_estimation_questionnaire()
        return {
            "schema_version": questionnaire["schema_version"],
            "blocking": questionnaire["blocking"],
            "questions": questionnaire["questions"],
            "fabric_width_presets": list(FABRIC_WIDTH_PRESETS),
            "warnings": [],
            "errors": [],
        }

    def _create_job(self, arguments: dict[str, Any]) -> ToolResponse:
        record = self.store.create_job(
            job_name=arguments["job_name"],
            user_note=arguments.get("user_note", ""),
        )
        return {
            "job_id": record.job_id,
            "warnings": [],
            "errors": [],
        }

    def _register_input_file(self, arguments: dict[str, Any]) -> ToolResponse:
        try:
            content = b64decode(arguments["content_base64"], validate=True)
        except (Base64DecodeError, ValueError):
            return _error_response("TOOL_VALIDATION_FAILED", "Tool input validation failed.")

        file_id = self.store.register_input_file(arguments["job_id"], arguments["file_name"], content)
        return {
            "job_id": arguments["job_id"],
            "file_id": file_id,
            "file_name": arguments["file_name"],
            "warnings": [],
            "errors": [],
        }

    def _parse_dxf(self, arguments: dict[str, Any]) -> ToolResponse:
        job_id = arguments["job_id"]
        file_path = self.store.get_file_path(job_id, arguments["file_id"])
        result = parse_dxf_file(file_path)
        warnings, errors = _split_messages(result.messages)
        response: ToolResponse = {
            "job_id": job_id,
            "entity_summary": _entity_summary(result),
            "warnings": warnings,
            "errors": errors,
        }
        if errors:
            return response

        response["dxf_parse_id"] = self.store.store_dxf_parse(job_id, result)
        return response

    def _extract_pattern_pieces(self, arguments: dict[str, Any]) -> ToolResponse:
        job_id = arguments["job_id"]
        if arguments["extraction_mode"] != "closed_polylines_only":
            return _error_response("UNSUPPORTED_EXTRACTION_MODE", "Extraction mode is outside the MVP scope.")

        parse_result = self.store.get_dxf_parse(job_id, arguments["dxf_parse_id"])
        warnings, errors = _split_messages(parse_result.messages)
        if errors:
            return {
                "job_id": job_id,
                "piece_summary": [],
                "warnings": warnings,
                "errors": errors,
            }

        pieces = _filter_pieces(parse_result.piece_candidates, arguments.get("outline_layer_names") or [])
        if not pieces:
            return {
                "job_id": job_id,
                "piece_summary": [],
                "warnings": warnings,
                "errors": [_message("NO_PATTERN_PIECES_FOUND", "No closed pattern pieces were found.", "blocker")],
            }

        piece_set_id = self.store.store_piece_set(job_id, pieces)
        if not arguments.get("grainline_layer_names"):
            warnings.append(_message("GRAINLINE_NOT_DETECTED", "No grainline layer names were provided.", "warning"))
        return {
            "job_id": job_id,
            "piece_set_id": piece_set_id,
            "piece_summary": [_piece_summary(piece) for piece in pieces],
            "warnings": warnings,
            "errors": [],
        }

    def _calculate_piece_metrics(self, arguments: dict[str, Any]) -> ToolResponse:
        job_id = arguments["job_id"]
        pieces = self.store.get_piece_set(job_id, arguments["piece_set_id"])
        result = calculate_piece_set_metrics(
            pieces,
            unit=arguments["unit"],
            dxf_unit_hint=arguments.get("dxf_unit_hint", "auto"),
            fabric_width=arguments.get("fabric_width"),
            fabric_width_unit=arguments.get("fabric_width_unit"),
            seam_allowance_width=arguments.get("seam_allowance_width", 0.0),
        )
        warnings, errors = _split_messages(result.messages)
        response: ToolResponse = {
            "job_id": job_id,
            "piece_metrics": [_piece_metrics(metric) for metric in result.metrics],
            "total_area": _total_area(result),
            "dxf_unit": result.source_unit,
            "unit_scale": result.unit_scale,
            "warnings": warnings,
            "errors": errors,
        }
        if errors:
            return response

        response["metrics_id"] = self.store.store_metrics(job_id, result)
        return response

    def _estimate_marker_layout(self, arguments: dict[str, Any]) -> ToolResponse:
        job_id = arguments["job_id"]
        if arguments.get("one_way_fabric") is True and arguments.get("grainline_status", "unknown") == "missing":
            return {
                "job_id": job_id,
                "warnings": [],
                "errors": [
                    _message(
                        "MISSING_GRAINLINE_ON_ONE_WAY_FABRIC",
                        "Grainline is required for one-way fabric before estimating marker layout.",
                        "blocker",
                    )
                ],
            }

        metrics = self.store.get_metrics(job_id, arguments["metrics_id"])
        grainline_status = arguments.get("grainline_status", "unknown")
        one_way_fabric = arguments.get("one_way_fabric")
        result = run_estimate_marker_layout(
            metrics,
            fabric_width=arguments["fabric_width"],
            fabric_width_unit=arguments["fabric_width_unit"],
            rotation_allowed_degrees=arguments["rotation_allowed_degrees"],
            clearance=arguments["clearance"],
        )
        result = replace(result, grainline_status=grainline_status, one_way_fabric=one_way_fabric)
        result = replace(result, messages=(*result.messages, *_rotation_policy_messages(result)))
        warnings, errors = _split_messages(result.messages)
        response = _layout_response(job_id, result, warnings, errors)
        if errors:
            return response

        response["layout_id"] = self.store.store_layout(job_id, result)
        return response

    def _render_marker_svg(self, arguments: dict[str, Any]) -> ToolResponse:
        job_id = arguments["job_id"]
        layout = self.store.get_layout(job_id, arguments["layout_id"])
        artifact_id = self.store.register_artifact(
            job_id,
            "marker_preview.svg",
            render_marker_svg(layout),
            media_type="image/svg+xml",
        )
        return {
            "job_id": job_id,
            "layout_id": arguments["layout_id"],
            "rendered": True,
            "artifact_id": artifact_id,
            "width": layout.fabric_width,
            "height": layout.marker_length,
            "unit": layout.unit,
            "warnings": [],
            "errors": [],
        }

    def _get_job_status(self, arguments: dict[str, Any]) -> ToolResponse:
        record = self.store.get_job(arguments["job_id"])
        return {
            "job_id": record.job_id,
            "stage": _job_stage(record),
            "object_counts": {
                "files": len(record.files),
                "dxf_parses": len(record.dxf_parses),
                "piece_sets": len(record.piece_sets),
                "metrics": len(record.metrics),
                "layouts": len(record.layouts),
                "artifacts": len(record.artifacts),
            },
            "warnings": [],
            "errors": [],
        }

    def _export_artifacts(self, arguments: dict[str, Any]) -> ToolResponse:
        job_id = arguments["job_id"]
        archive_id = self.store.export_artifacts_zip(job_id, arguments["artifact_ids"])
        archive = self.store.get_artifact(job_id, archive_id)
        return {
            "job_id": job_id,
            "archive_artifact_id": archive_id,
            "archive_format": arguments.get("archive_format", "zip"),
            "artifact_count": len(arguments["artifact_ids"]),
            "size_bytes": archive.path.stat().st_size,
            "warnings": [],
            "errors": [],
        }


def tools_list(registry: McpToolRegistry | None = None) -> dict[str, Any]:
    active_registry = registry or McpToolRegistry()
    return {"tools": active_registry.list_tools()}


def tools_call(name: str, arguments: dict[str, Any], registry: McpToolRegistry | None = None) -> ToolResponse:
    active_registry = registry or McpToolRegistry()
    return active_registry.call_tool(name, arguments)


def _filter_pieces(
    pieces: tuple[PolylineCandidate, ...],
    outline_layer_names: list[str],
) -> tuple[PolylineCandidate, ...]:
    if not outline_layer_names:
        return pieces
    allowed_layers = set(outline_layer_names)
    return tuple(piece for piece in pieces if piece.layer in allowed_layers)


def _entity_summary(result: Any) -> dict[str, Any]:
    layers = {
        item.layer
        for item in (*result.piece_candidates, *result.excluded_candidates)
        if getattr(item, "layer", None) is not None
    }
    return {
        "acad_version": result.acad_version,
        "entity_count": result.summary.total_entities,
        "entity_types": dict(result.summary.counts_by_type),
        "layer_count": len(layers),
        "candidate_layers": sorted({piece.layer for piece in result.piece_candidates}),
        "polyline_count": result.summary.polyline_count,
        "closed_polyline_count": result.summary.closed_polyline_count,
        "open_polyline_count": result.summary.open_polyline_count,
        "closed_lwpolyline_count": result.summary.closed_lwpolyline_count,
        "open_lwpolyline_count": result.summary.open_lwpolyline_count,
        "unsupported_entity_types": list(result.summary.unsupported_entity_types),
    }


def _piece_summary(piece: PolylineCandidate) -> dict[str, Any]:
    return {
        "piece_id": piece.piece_id,
        "piece_name": None,
        "closed": piece.closed,
        "has_grainline": False,
        "entity_source": "LWPOLYLINE",
        "estimated_point_count": len(piece.points),
    }


def _piece_metrics(metric: PieceMetrics) -> dict[str, Any]:
    return {
        "piece_id": metric.piece_id,
        "piece_name": None,
        "area": metric.area,
        "perimeter": metric.perimeter,
        "bbox": {"width": metric.bbox.width, "height": metric.bbox.height},
        "valid": True,
        "has_grainline": False,
        "unit": metric.unit,
        "point_count": metric.point_count,
        "seam_allowance_width": metric.seam_allowance_width,
        "source_unit": metric.source_unit,
        "unit_scale": metric.unit_scale,
    }


def _total_area(result: MetricsResult) -> float:
    return sum(metric.area for metric in result.metrics)


def _layout_response(
    job_id: str,
    result: LayoutResult,
    warnings: list[dict[str, str]],
    errors: list[dict[str, str]],
) -> ToolResponse:
    return {
        "job_id": job_id,
        "fabric_width": result.fabric_width,
        "marker_length": result.marker_length,
        "efficiency": result.efficiency,
        "clearance": result.clearance,
        "unit": result.unit,
        "total_piece_area": result.total_piece_area,
        "rotation_allowed_degrees": list(result.rotation_allowed_degrees),
        "grainline_status": result.grainline_status,
        "one_way_fabric": result.one_way_fabric,
        "layout_summary": [_placement_summary(placement) for placement in result.placements],
        "validity": {
            "within_fabric_width": result.within_fabric_width,
            "no_overlap": result.no_overlap,
            "overlaps": [
                {"first_piece_id": overlap.first_piece_id, "second_piece_id": overlap.second_piece_id}
                for overlap in result.overlaps
            ],
        },
        "warnings": warnings,
        "errors": errors,
    }


def _placement_summary(placement: Any) -> dict[str, Any]:
    return {
        "piece_id": placement.piece_id,
        "layer": placement.layer,
        "x": placement.x,
        "y": placement.y,
        "width": placement.width,
        "height": placement.height,
        "rotation_degrees": placement.rotation_degrees,
    }


def _rotation_policy_messages(result: LayoutResult) -> tuple[EngineMessage, ...]:
    if result.grainline_status == "present":
        return ()
    if all(rotation == 0 for rotation in result.rotation_allowed_degrees):
        return ()
    return (
        EngineMessage(
            code="ROTATION_WITHOUT_GRAINLINE",
            message="Rotation was allowed even though grainline was not detected; verify this before production use.",
            severity="warning",
        ),
    )


def _job_stage(record: Any) -> str:
    if record.artifacts:
        return "artifacts_available"
    if record.layouts:
        return "layout_estimated"
    if record.metrics:
        return "metrics_calculated"
    if record.piece_sets:
        return "pieces_extracted"
    if record.dxf_parses:
        return "dxf_parsed"
    if record.files:
        return "file_registered"
    return "created"


def _split_messages(messages: tuple[EngineMessage, ...]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for engine_message in messages:
        public = _message(engine_message.code, engine_message.message, engine_message.severity)
        if engine_message.severity == "blocker":
            errors.append(public)
        else:
            warnings.append(public)
    return warnings, errors


def _message(code: str, message: str, severity: str) -> dict[str, str]:
    return {
        "code": code,
        "message": _redact_internal_path(message),
        "severity": severity,
    }


def _error_response(code: str, message: str) -> ToolResponse:
    return {
        "warnings": [],
        "errors": [_message(code, message, "blocker")],
    }


def _redact_internal_path(message: str) -> str:
    clean = " ".join(str(message).split())
    if re.search(r"([A-Za-z]:\\|\\\\|/[A-Za-z0-9_.-]+/|[A-Za-z]:/)", clean):
        return "Internal file access failed."
    return clean[:500]
