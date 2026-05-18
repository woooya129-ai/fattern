"""Tool registry and wrappers for Fattern MCP calls."""

from __future__ import annotations

import json
import os
import re
from base64 import b64decode
from binascii import Error as Base64DecodeError
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import replace
from math import hypot
from pathlib import Path
from typing import Any, Callable

from fattern.engine import (
    DxfLineEntity,
    EngineMessage,
    LayoutResult,
    MetricsResult,
    PieceMetrics,
    PolylineCandidate,
    estimate_marker_layout as run_estimate_marker_layout,
    parse_dxf_file,
)
from fattern.geometry import BoundingBox
from fattern.engine.metrics import calculate_piece_set_metrics
from fattern.jobs import JobError, JobStore, SecurityError, resolve_workspace_file
from fattern.quote import build_quote_decision
from fattern.report import PieceReportMetadata, partial_csv_fields, render_marker_csv, render_marker_pdf, render_marker_report
from fattern.render import render_marker_svg
from fattern.runs import default_output_root, default_web_base_url, persist_run_outputs

from .schemas import TOOL_SCHEMAS, list_tool_definitions
from .validation import ToolValidationError, validate_input

ToolResponse = dict[str, Any]


class McpToolRegistry:
    def __init__(
        self,
        store: JobStore | None = None,
        *,
        workspace_root: Path | str | None = None,
        output_root: Path | str | None = None,
        web_base_url: str | None = None,
        persist_runs: bool = False,
        allow_workspace_paths: bool = True,
    ) -> None:
        self.store = store or JobStore()
        self.workspace_root = _default_workspace_root(workspace_root)
        self.output_root = Path(output_root) if output_root is not None else default_output_root()
        self.web_base_url = web_base_url if web_base_url is not None else default_web_base_url()
        self.persist_runs = persist_runs
        self.allow_workspace_paths = allow_workspace_paths
        self._handlers: dict[str, Callable[[dict[str, Any]], ToolResponse]] = {
            "get_estimation_questionnaire": self._get_estimation_questionnaire,
            "create_job": self._create_job,
            "register_input_file": self._register_input_file,
            "estimate_workspace_dxf": self._estimate_workspace_dxf,
            "parse_dxf": self._parse_dxf,
            "extract_pattern_pieces": self._extract_pattern_pieces,
            "calculate_piece_metrics": self._calculate_piece_metrics,
            "estimate_marker_layout": self._estimate_marker_layout,
            "render_marker_svg": self._render_marker_svg,
            "get_job_status": self._get_job_status,
            "export_artifacts": self._export_artifacts,
            "calculate_marker_yield": self._calculate_marker_yield,
        }

    def list_tools(self) -> list[dict]:
        tools = list_tool_definitions()
        if not self.allow_workspace_paths:
            tools = [tool for tool in tools if tool["name"] != "estimate_workspace_dxf"]
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResponse:
        if name == "estimate_workspace_dxf" and not self.allow_workspace_paths:
            return _error_response(
                "WORKSPACE_PATHS_DISABLED",
                "Workspace-relative path tools are disabled for this MCP surface.",
            )
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

    def _estimate_workspace_dxf(self, arguments: dict[str, Any]) -> ToolResponse:
        try:
            dxf_path = _resolve_workspace_relative_dxf(self.workspace_root, arguments["relative_path"])
        except SecurityError as exc:
            return _error_response(exc.code, exc.public_message)

        record = self.store.create_job(f"workspace:{dxf_path.stem}")
        file_id = self.store.register_input_file(record.job_id, dxf_path.name, dxf_path.read_bytes())
        request = _workspace_marker_yield_request(file_id, arguments)
        response = self.call_tool("calculate_marker_yield", request)
        response["workspace_relative_path"] = _workspace_display_path(self.workspace_root, dxf_path)
        return response

    def _parse_dxf(self, arguments: dict[str, Any]) -> ToolResponse:
        job_id = arguments["job_id"]
        file_path = self.store.get_file_path(job_id, arguments["file_id"])
        result = parse_dxf_file(file_path)
        warnings, errors = _split_messages(result.messages)
        response: ToolResponse = {
            "job_id": job_id,
            "entity_summary": _entity_summary(result),
            "layer_audit": _layer_audit(result, ()),
            "warnings": warnings,
            "errors": errors,
        }
        if errors:
            return response

        response["dxf_parse_id"] = self.store.store_dxf_parse(job_id, result)
        return response

    def _extract_pattern_pieces(self, arguments: dict[str, Any]) -> ToolResponse:
        job_id = arguments["job_id"]
        extraction_mode = arguments["extraction_mode"]

        parse_result = self.store.get_dxf_parse(job_id, arguments["dxf_parse_id"])
        warnings, errors = _split_messages(parse_result.messages)
        if extraction_mode != "closed_polylines_only":
            warnings.append(
                _message(
                    "EXTRACTION_MODE_FALLBACK",
                    f"{extraction_mode} uses the deterministic closed-outline fallback parser in v0.7.1.",
                    "warning",
                )
            )
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

        pieces, semantic_warnings = _attach_grainline_metadata(
            pieces,
            parse_result.line_entities,
            arguments.get("grainline_layer_names") or [],
        )
        warnings.extend(semantic_warnings)
        piece_set_id = self.store.store_piece_set(job_id, pieces)
        if not parse_result.line_entities:
            warnings.append(_message("GRAINLINE_NOT_DETECTED", "No grainline line entities were detected.", "warning"))
        return {
            "job_id": job_id,
            "piece_set_id": piece_set_id,
            "piece_summary": [_piece_summary(piece) for piece in pieces],
            "layer_audit": _layer_audit(parse_result, arguments.get("grainline_layer_names") or []),
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
        if arguments.get("one_way_fabric") is True and arguments.get("grainline_status", "unknown") != "present":
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
            cuttable_width=arguments.get("cuttable_width"),
            spacing=arguments.get("spacing"),
            nap_direction=arguments.get("nap_direction"),
            one_way_fabric=one_way_fabric,
            grainline_status=grainline_status,
            grainline_required=arguments.get("grainline_required"),
            fabric_type=arguments.get("fabric_type"),
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

    def _calculate_marker_yield(self, arguments: dict[str, Any]) -> ToolResponse:
        validation_error = _validate_marker_yield_request(arguments)
        if validation_error is not None:
            return validation_error

        job_record, file_record = self.store.resolve_input_file(arguments["pattern_file_id"])
        if file_record.path.suffix.lower() != ".dxf":
            return _error_response("UNSUPPORTED_FILE_TYPE", "Pattern input must be a DXF file.")

        job_id = job_record.job_id
        warnings = _marker_yield_preflight_warnings(arguments)
        tool_calls: list[str] = []
        state: ToolResponse = {
            "status": "running",
            "job_id": job_id,
            "pattern_file_id": arguments["pattern_file_id"],
            "source_name": file_record.original_name,
            "tool_calls": tool_calls,
            "warnings": warnings,
            "errors": [],
            "store": self.store,
            "registry": self,
        }

        effective_width = arguments.get("cuttable_width") or arguments["fabric_width"]
        seam_allowance = arguments["seam_allowance"]
        seam_allowance_width = _resolve_seam_allowance_width(seam_allowance, arguments["unit"])
        if seam_allowance["status"] == "excluded" and seam_allowance.get("fallback_width") is None:
            _extend_unique_messages(
                warnings,
                [
                    _message(
                        "SEAM_ALLOWANCE_DEFAULT_APPLIED",
                        f"Seam allowance fallback default for {arguments['unit']} was applied.",
                        "warning",
                    )
                ],
            )

        parse_response = self.call_tool(
            "parse_dxf",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "file_id": arguments["pattern_file_id"],
                "unit_hint": "auto",
            },
        )
        tool_calls.append("parse_dxf")
        _extend_unique_messages(warnings, parse_response.get("warnings", []))
        if _has_blocker(parse_response):
            return _finalize_marker_yield(state, "parse_dxf", parse_response.get("errors", []))

        dxf_parse_id = parse_response["dxf_parse_id"]
        state["dxf_parse_id"] = dxf_parse_id

        extract_response = self.call_tool(
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
        tool_calls.append("extract_pattern_pieces")
        _extend_unique_messages(warnings, extract_response.get("warnings", []))
        if _has_blocker(extract_response):
            return _finalize_marker_yield(state, "extract_pattern_pieces", extract_response.get("errors", []))

        piece_set_id = extract_response["piece_set_id"]
        state["piece_set_id"] = piece_set_id
        grainline_status = _infer_marker_yield_grainline_status(extract_response, arguments["grainline_required"])
        grainline_errors = _marker_yield_grainline_errors(arguments, grainline_status)
        if grainline_errors:
            return _finalize_marker_yield(state, "extract_pattern_pieces", grainline_errors)
        pieces = self.store.get_piece_set(job_id, piece_set_id)
        expanded_pieces, piece_metadata, size_ratio_warnings = _expand_piece_set_for_size_ratio(
            pieces,
            arguments.get("size_ratio", {}),
            arguments.get("piece_quantity", {}),
        )
        _extend_unique_messages(warnings, size_ratio_warnings)
        expanded_pieces, shrinkage_warnings = _apply_shrinkage_to_pieces(
            expanded_pieces,
            _marker_yield_shrinkage(arguments),
        )
        _extend_unique_messages(warnings, shrinkage_warnings)
        if expanded_pieces != pieces:
            piece_set_id = self.store.store_piece_set(job_id, expanded_pieces)
            state["piece_set_id"] = piece_set_id

        metrics_response = self.call_tool(
            "calculate_piece_metrics",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "piece_set_id": piece_set_id,
                "unit": arguments["unit"],
                "dxf_unit_hint": "auto",
                "fabric_width": effective_width,
                "fabric_width_unit": arguments["unit"],
                "seam_allowance_width": seam_allowance_width,
            },
        )
        tool_calls.append("calculate_piece_metrics")
        _extend_unique_messages(warnings, metrics_response.get("warnings", []))
        if _has_blocker(metrics_response):
            return _finalize_marker_yield(state, "calculate_piece_metrics", metrics_response.get("errors", []))

        metrics_id = metrics_response["metrics_id"]
        state["metrics_id"] = metrics_id
        state["dxf_unit"] = metrics_response.get("dxf_unit")
        state["unit_scale"] = metrics_response.get("unit_scale")
        one_way_fabric = _marker_yield_one_way_fabric(arguments["nap_direction"])

        layout_response = self.call_tool(
            "estimate_marker_layout",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "metrics_id": metrics_id,
                "fabric_width": effective_width,
                "fabric_width_unit": arguments["unit"],
                "rotation_allowed_degrees": list(arguments["allowed_rotation"]),
                "clearance": arguments["spacing"],
                "nap_direction": arguments["nap_direction"],
                "one_way_fabric": one_way_fabric,
                "grainline_status": grainline_status,
                "grainline_required": arguments["grainline_required"],
                "fabric_type": arguments["fabric_type"],
            },
        )
        tool_calls.append("estimate_marker_layout")
        _extend_unique_messages(warnings, layout_response.get("warnings", []))
        if _has_blocker(layout_response):
            return _finalize_marker_yield(state, "estimate_marker_layout", layout_response.get("errors", []))

        layout_id = layout_response["layout_id"]
        state["layout_id"] = layout_id
        state["layout"] = _public_layout(layout_response)

        render_response = self.call_tool(
            "render_marker_svg",
            {
                "schema_version": "1.0",
                "job_id": job_id,
                "layout_id": layout_id,
            },
        )
        tool_calls.append("render_marker_svg")
        _extend_unique_messages(warnings, render_response.get("warnings", []))
        if _has_blocker(render_response):
            return _finalize_marker_yield(state, "render_marker_svg", render_response.get("errors", []))

        layout_result = self.store.get_layout(job_id, layout_id)
        parse_result = self.store.get_dxf_parse(job_id, dxf_parse_id)
        metrics_result = self.store.get_metrics(job_id, metrics_id)
        csv_partial = list(partial_csv_fields(_resolved_csv_metadata_fields(piece_metadata)))

        _extend_unique_messages(
            warnings,
            [
                _message(
                    "REPORT_CSV_PARTIAL_FIELDS",
                    f"report.csv leaves unavailable piece metadata fields empty: {', '.join(csv_partial) if csv_partial else 'none'}.",
                    "warning",
                )
            ],
        )
        quote_decision = build_quote_decision(
            marker_length=layout_result.marker_length,
            unit=layout_result.unit,
            allowance_policy=arguments.get("allowance_policy"),
            warnings=warnings,
        )

        report_text = render_marker_report(
            layout_result,
            warnings=_engine_warnings(warnings),
            excluded_pieces=parse_result.excluded_candidates,
            csv_partial_fields=csv_partial,
            quote_decision=quote_decision,
        )
        report_artifact_id = self.store.register_artifact(
            job_id,
            "marker_report.md",
            report_text,
            media_type="text/markdown",
        )
        pdf_artifact_id = self.store.register_artifact(
            job_id,
            "marker_report.pdf",
            render_marker_pdf(report_text),
            media_type="application/pdf",
        )

        csv_text = render_marker_csv(
            _layout_result_in_mm(layout_result),
            piece_metrics=_piece_metrics_in_mm(metrics_result),
            piece_metadata=piece_metadata,
        )
        csv_artifact_id = self.store.register_artifact(
            job_id,
            "report.csv",
            csv_text,
            media_type="text/csv",
        )

        response: ToolResponse = {
            "status": "completed",
            "job_id": job_id,
            "pattern_file_id": arguments["pattern_file_id"],
            "stopped_at": "completed",
            "tool_calls": tool_calls,
            "warnings": warnings,
            "errors": [],
            "dxf_parse_id": dxf_parse_id,
            "piece_set_id": piece_set_id,
            "metrics_id": metrics_id,
            "layout_id": layout_id,
            "dxf_unit": metrics_response.get("dxf_unit"),
            "unit_scale": metrics_response.get("unit_scale"),
            "layout": _public_layout(layout_response),
            "minimum_yield": quote_decision["minimum_yield"],
            "quote_yield": quote_decision["quote_yield"],
            "allowance_breakdown": quote_decision["allowance_breakdown"],
            "allowance_reasons": quote_decision["allowance_reasons"],
            "allowance_policy": quote_decision["allowance_policy"],
            "confidence": quote_decision["confidence"],
            "partial_csv_fields": csv_partial,
            "artifact_ids": {
                "marker_preview_svg": render_response["artifact_id"],
                "marker_report_md": report_artifact_id,
                "marker_report_pdf": pdf_artifact_id,
                "report_csv": csv_artifact_id,
            },
        }

        from fattern.orchestration.chain import validate_final_report

        try:
            validate_final_report(response, layout_result, report_text, excluded_piece_ids=_excluded_report_ids(parse_result))
        except Exception as exc:
            return _finalize_marker_yield(
                state,
                "render_marker_report",
                [_message("REPORT_VALIDATION_FAILED", str(exc), "blocker")],
            )

        result_artifact_id = self.store.register_artifact(
            job_id,
            "result.json",
            "{}",
            media_type="application/json",
        )
        response["artifact_ids"]["result_json"] = result_artifact_id
        response["export_artifact_ids"] = [
            result_artifact_id,
            render_response["artifact_id"],
            report_artifact_id,
            pdf_artifact_id,
            csv_artifact_id,
        ]
        if self.persist_runs:
            response, _run = persist_run_outputs(
                self.store,
                response,
                source_name=file_record.original_name,
                output_root=self.output_root,
                web_base_url=self.web_base_url,
            )
        self.store.get_artifact(job_id, result_artifact_id).path.write_text(
            json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return response


def tools_list(registry: McpToolRegistry | None = None) -> dict[str, Any]:
    active_registry = registry or McpToolRegistry()
    return {"tools": active_registry.list_tools()}


def tools_call(name: str, arguments: dict[str, Any], registry: McpToolRegistry | None = None) -> ToolResponse:
    active_registry = registry or McpToolRegistry()
    return active_registry.call_tool(name, arguments)


def _default_workspace_root(value: Path | str | None) -> Path:
    if value is not None:
        return Path(value).resolve()
    configured = (
        os.environ.get("FATTERN_WORKSPACE_ROOT")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or os.environ.get("CODEX_WORKSPACE")
    )
    return Path(configured).resolve() if configured else Path.cwd().resolve()


def _resolve_workspace_relative_dxf(workspace_root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise SecurityError("INVALID_WORKSPACE_PATH", "Workspace path is required.")
    candidate = Path(relative_path.strip())
    if candidate.is_absolute() or candidate.drive or candidate.root:
        raise SecurityError("INVALID_WORKSPACE_PATH", "Only workspace-relative DXF paths are allowed.")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise SecurityError("INVALID_WORKSPACE_PATH", "Workspace path failed validation.")
    if candidate.suffix.lower() != ".dxf":
        raise SecurityError("UNSUPPORTED_FILE_TYPE", "Pattern input must be a DXF file.")
    return resolve_workspace_file(workspace_root, workspace_root / candidate, allowed_suffixes=frozenset({".dxf"}))


def _workspace_marker_yield_request(pattern_file_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    request = {
        "schema_version": "1.0",
        "pattern_file_id": pattern_file_id,
        "fabric_width": arguments["fabric_width"],
        "unit": arguments["unit"],
        "size_ratio": arguments.get("size_ratio", {}),
        "piece_quantity": arguments.get("piece_quantity", {}),
        "spacing": arguments.get("spacing", 0.2),
        "allowed_rotation": arguments.get("allowed_rotation", [0]),
        "grainline_required": arguments.get("grainline_required", False),
        "nap_direction": arguments.get("nap_direction", "two_way"),
        "shrinkage_percent": arguments.get("shrinkage_percent", 0),
        "fabric_type": arguments.get("fabric_type", "unknown"),
        "seam_allowance": arguments.get("seam_allowance", {"status": "included"}),
        "allowance_policy": arguments.get("allowance_policy", {"mode": "fast_quote"}),
    }
    for optional in ("cuttable_width", "shrinkage", "stretch_direction"):
        if optional in arguments:
            request[optional] = arguments[optional]
    return request


def _workspace_display_path(workspace_root: Path, path: Path) -> str:
    try:
        return path.relative_to(workspace_root).as_posix()
    except ValueError:
        return path.name


def _filter_pieces(
    pieces: tuple[PolylineCandidate, ...],
    outline_layer_names: list[str],
) -> tuple[PolylineCandidate, ...]:
    if not outline_layer_names:
        return pieces
    allowed_layers = set(outline_layer_names)
    return tuple(piece for piece in pieces if piece.layer in allowed_layers)


def _attach_grainline_metadata(
    pieces: tuple[PolylineCandidate, ...],
    line_entities: tuple[DxfLineEntity, ...],
    grainline_layer_names: list[str],
) -> tuple[tuple[PolylineCandidate, ...], list[dict[str, str]]]:
    explicit_layers = {name.strip().lower() for name in grainline_layer_names if name.strip()}
    candidate_lines: list[tuple[DxfLineEntity, float, str]] = []
    for line in line_entities:
        confidence, source = _grainline_line_confidence(line, explicit_layers)
        if confidence > 0:
            candidate_lines.append((line, confidence, source))

    warnings: list[dict[str, str]] = []
    if candidate_lines and not explicit_layers:
        warnings.append(
            _message(
                "GRAINLINE_LAYER_CANDIDATE_DETECTED",
                "Grainline line candidates were detected by deterministic layer rules; verify before production use.",
                "warning",
            )
        )
    if any(source == "aama_astm_candidate" for _line, _confidence, source in candidate_lines):
        warnings.append(
            _message(
                "AAMA_ASTM_LAYER_MAPPING_UNVERIFIED",
                "Numeric DXF layer grainline mapping is treated as a low-confidence candidate because local evidence is insufficient.",
                "warning",
            )
        )
    internal_count = max(0, len(line_entities) - len(candidate_lines))
    if internal_count:
        warnings.append(
            _message(
                "INTERNAL_LINE_EXCLUDED",
                f"{internal_count} LINE entities were treated as internal lines and excluded from area and bbox metrics.",
                "warning",
            )
        )

    annotated: list[PolylineCandidate] = []
    for piece in pieces:
        matching = _matching_grainline(piece, candidate_lines)
        if matching is None:
            annotated.append(piece)
            continue
        line, confidence, _source = matching
        annotated.append(
            replace(
                piece,
                has_grainline=True,
                grainline_confidence=confidence,
                grainline_layer=line.layer,
                grainline_start=line.start,
                grainline_end=line.end,
            )
        )
    return tuple(annotated), warnings


def _grainline_line_confidence(line: DxfLineEntity, explicit_layers: set[str]) -> tuple[float, str]:
    normalized = line.layer.strip().lower()
    if normalized in explicit_layers:
        return 1.0, "explicit"
    compact = normalized.replace("_", "").replace("-", "").replace(" ", "")
    if compact in {"grain", "grainline", "grainln"}:
        return 0.8, "layer_name"
    if normalized == "7":
        return 0.6, "aama_astm_candidate"
    return 0.0, ""


def _matching_grainline(
    piece: PolylineCandidate,
    candidate_lines: list[tuple[DxfLineEntity, float, str]],
) -> tuple[DxfLineEntity, float, str] | None:
    for line, confidence, source in candidate_lines:
        if _line_midpoint_inside_piece(line, piece):
            return line, confidence, source
    return None


def _line_midpoint_inside_piece(line: DxfLineEntity, piece: PolylineCandidate) -> bool:
    x = (line.start[0] + line.end[0]) / 2.0
    y = (line.start[1] + line.end[1]) / 2.0
    return _point_in_polygon((x, y), piece.points)


def _point_in_polygon(point: tuple[float, float], polygon: tuple[tuple[float, float], ...]) -> bool:
    x, y = point
    inside = False
    j = len(polygon) - 1
    for i, current in enumerate(polygon):
        previous = polygon[j]
        intersects = (current[1] > y) != (previous[1] > y)
        if intersects:
            x_intersection = (previous[0] - current[0]) * (y - current[1]) / (previous[1] - current[1]) + current[0]
            if x <= x_intersection:
                inside = not inside
        j = i
    return inside


def _entity_summary(result: Any) -> dict[str, Any]:
    layers = {
        item.layer
        for item in (*result.piece_candidates, *result.excluded_candidates, *result.line_entities, *result.text_entities)
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
        "line_entity_count": len(result.line_entities),
        "text_entity_count": len(result.text_entities),
    }


def _layer_audit(result: Any, grainline_layer_names: Sequence[str]) -> list[dict[str, Any]]:
    explicit_layers = {name.strip().lower() for name in grainline_layer_names if name.strip()}
    rows: dict[str, dict[str, Any]] = {}

    def row(layer: str | None) -> dict[str, Any]:
        key = layer or "0"
        if key not in rows:
            rows[key] = {
                "layer": key,
                "entity_counts": {},
                "grainline_rule_source": None,
                "grainline_confidence": None,
                "mapping_status": "not_grainline_candidate",
            }
        return rows[key]

    def increment(layer: str | None, entity_type: str) -> None:
        item = row(layer)
        counts = item["entity_counts"]
        counts[entity_type] = counts.get(entity_type, 0) + 1

    for piece in result.piece_candidates:
        increment(piece.layer, "PIECE_CANDIDATE")
    for excluded in result.excluded_candidates:
        increment(excluded.layer, excluded.entity_type)
    for text in result.text_entities:
        increment(text.layer, "TEXT")
    for line in result.line_entities:
        item = row(line.layer)
        counts = item["entity_counts"]
        counts["LINE"] = counts.get("LINE", 0) + 1
        confidence, source = _grainline_line_confidence(line, explicit_layers)
        if confidence <= 0:
            continue
        if item["grainline_confidence"] is None or confidence > item["grainline_confidence"]:
            item["grainline_rule_source"] = source
            item["grainline_confidence"] = confidence
            item["mapping_status"] = _layer_mapping_status(source)

    return [rows[layer] for layer in sorted(rows)]


def _layer_mapping_status(source: str) -> str:
    if source == "explicit":
        return "explicit_grainline_rule"
    if source == "aama_astm_candidate":
        return "aama_astm_candidate_unverified"
    if source:
        return "deterministic_candidate"
    return "not_grainline_candidate"


def _piece_summary(piece: PolylineCandidate) -> dict[str, Any]:
    return {
        "piece_id": piece.piece_id,
        "piece_name": piece.piece_name,
        "size": piece.size,
        "closed": piece.closed,
        "has_grainline": piece.has_grainline,
        "grainline_confidence": piece.grainline_confidence,
        "grainline_layer": piece.grainline_layer,
        "entity_source": "LWPOLYLINE",
        "estimated_point_count": len(piece.points),
    }


def _piece_metrics(metric: PieceMetrics) -> dict[str, Any]:
    return {
        "piece_id": metric.piece_id,
        "piece_name": metric.piece_name,
        "size": metric.size,
        "area": metric.area,
        "perimeter": metric.perimeter,
        "bbox": {"width": metric.bbox.width, "height": metric.bbox.height},
        "valid": True,
        "has_grainline": metric.has_grainline,
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


def _validate_marker_yield_request(arguments: dict[str, Any]) -> ToolResponse | None:
    size_ratio = arguments.get("size_ratio", {})
    if not isinstance(size_ratio, dict):
        return _error_response("TOOL_VALIDATION_FAILED", "Tool input validation failed.")
    for size_name, quantity in size_ratio.items():
        if not isinstance(size_name, str) or not size_name.strip():
            return _error_response("TOOL_VALIDATION_FAILED", "Tool input validation failed.")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            return _error_response("TOOL_VALIDATION_FAILED", "Tool input validation failed.")

    piece_quantity = arguments.get("piece_quantity", {})
    if not isinstance(piece_quantity, dict):
        return _error_response("TOOL_VALIDATION_FAILED", "Tool input validation failed.")
    for piece_id, quantity in piece_quantity.items():
        if not isinstance(piece_id, str) or not piece_id.strip():
            return _error_response("TOOL_VALIDATION_FAILED", "Tool input validation failed.")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            return _error_response("TOOL_VALIDATION_FAILED", "Tool input validation failed.")

    cuttable_width = arguments.get("cuttable_width")
    if cuttable_width is not None and cuttable_width > arguments["fabric_width"]:
        return _error_response(
            "INVALID_CUTTABLE_WIDTH",
            "cuttable_width must not be greater than fabric_width.",
        )

    shrinkage = _marker_yield_shrinkage(arguments)
    if shrinkage["length_percent"] >= 100 or shrinkage["width_percent"] >= 100:
        return _error_response(
            "INVALID_SHRINKAGE_PERCENT",
            "shrinkage percent values must be less than 100.",
        )

    if arguments.get("nap_direction") == "unknown":
        return _error_response(
            "NAP_DIRECTION_UNKNOWN",
            "nap_direction must be explicitly set before calculating marker yield.",
        )

    if arguments.get("nap_direction") == "one_way" and 180 in arguments.get("allowed_rotation", []):
        return _error_response(
            "NAP_ROTATION_NOT_ALLOWED",
            "nap_direction=one_way does not allow 180 degree rotation.",
        )

    seam_allowance = arguments.get("seam_allowance", {})
    if seam_allowance.get("status") == "unknown":
        return _error_response(
            "SEAM_ALLOWANCE_STATUS_UNKNOWN",
            "Seam allowance status must be included or excluded for calculate_marker_yield.",
        )
    return None


def _marker_yield_preflight_warnings(arguments: dict[str, Any]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if arguments.get("cuttable_width") is not None:
        warnings.append(
            _message(
                "CUTTABLE_WIDTH_APPLIED",
                "cuttable_width was used instead of fabric_width for marker estimation.",
                "warning",
            )
        )
    if arguments.get("fabric_type") != "unknown":
        warnings.append(
            _message(
                "FABRIC_TYPE_POLICY_PARTIAL",
                "fabric_type-specific policy is only partially applied in the current MCP layer.",
                "warning",
            )
        )
    if arguments.get("fabric_type") == "knit":
        warnings.append(
            _message(
                "STRETCH_DIRECTION_NOT_APPLIED",
                "fabric_type=knit accepts stretch_direction, but stretch matching is not applied in the current marker engine.",
                "warning",
            )
        )
    return warnings


def _expand_piece_set_for_size_ratio(
    pieces: tuple[PolylineCandidate, ...],
    size_ratio: dict[str, Any],
    piece_quantity: dict[str, Any],
) -> tuple[tuple[PolylineCandidate, ...], dict[str, PieceReportMetadata], list[dict[str, str]]]:
    if not size_ratio:
        return _expand_piece_set_for_quantities(pieces, piece_quantity)

    expanded: list[PolylineCandidate] = []
    metadata: dict[str, PieceReportMetadata] = {}
    for size_index, (size_name, quantity) in enumerate(size_ratio.items(), start=1):
        for piece in pieces:
            requested_piece_quantity = _piece_quantity_for(piece, piece_quantity)
            for copy_index in range(1, int(quantity) * requested_piece_quantity + 1):
                piece_id = f"{piece.piece_id}_s{size_index:02d}_q{copy_index:02d}"
                expanded.append(replace(piece, piece_id=piece_id))
                metadata[piece_id] = PieceReportMetadata(
                    piece_name=piece.piece_name,
                    size=str(size_name),
                    quantity=1,
                    grainline_status="present" if piece.has_grainline else None,
                )

    warnings = [
        _message(
            "SIZE_RATIO_BASE_SIZE_REPLICATED",
            "size_ratio was applied by replicating base-size outlines; grading differences were not inferred.",
            "warning",
        )
    ]
    if any(_piece_quantity_for(piece, piece_quantity) != 1 for piece in pieces):
        warnings.append(
            _message(
                "PIECE_QUANTITY_APPLIED",
                "piece_quantity was applied by replicating matching base-size outlines.",
                "warning",
            )
        )
    return tuple(expanded), metadata, warnings


def _expand_piece_set_for_quantities(
    pieces: tuple[PolylineCandidate, ...],
    piece_quantity: dict[str, Any],
) -> tuple[tuple[PolylineCandidate, ...], dict[str, PieceReportMetadata], list[dict[str, str]]]:
    expanded: list[PolylineCandidate] = []
    metadata: dict[str, PieceReportMetadata] = {}
    changed = False
    for piece in pieces:
        quantity = _piece_quantity_for(piece, piece_quantity)
        changed = changed or quantity != 1
        for copy_index in range(1, quantity + 1):
            piece_id = piece.piece_id if quantity == 1 else f"{piece.piece_id}_q{copy_index:02d}"
            expanded.append(replace(piece, piece_id=piece_id))
            metadata[piece_id] = PieceReportMetadata(
                piece_name=piece.piece_name,
                size=piece.size,
                quantity=1,
                grainline_status="present" if piece.has_grainline else None,
            )
    warnings = [
        _message(
            "PIECE_QUANTITY_APPLIED",
            "piece_quantity was applied by replicating matching base-size outlines.",
            "warning",
        )
    ] if changed else []
    return tuple(expanded), metadata, warnings


def _piece_quantity_for(piece: PolylineCandidate, piece_quantity: dict[str, Any]) -> int:
    value = piece_quantity.get(piece.piece_id, piece_quantity.get("*", 1))
    return int(value)


def _apply_shrinkage_to_pieces(
    pieces: tuple[PolylineCandidate, ...],
    shrinkage: dict[str, float],
) -> tuple[tuple[PolylineCandidate, ...], list[dict[str, str]]]:
    length_percent = float(shrinkage["length_percent"])
    width_percent = float(shrinkage["width_percent"])
    if length_percent <= 0 and width_percent <= 0:
        return pieces, []
    if not pieces or any(piece.grainline_start is None or piece.grainline_end is None for piece in pieces):
        return (
            pieces,
            [
                _message(
                    "SHRINKAGE_PERCENT_NOT_APPLIED",
                    "shrinkage_percent requires piece-level grainline and was not applied.",
                    "warning",
                )
            ],
        )

    length_scale = 100.0 / (100.0 - length_percent) if length_percent > 0 else 1.0
    width_scale = 100.0 / (100.0 - width_percent) if width_percent > 0 else 1.0
    expanded = tuple(
        replace(piece, points=_scale_piece_along_grainline(piece, length_scale, width_scale))
        for piece in pieces
    )
    return (
        expanded,
        [
            _message(
                "SHRINKAGE_APPLIED",
                f"shrinkage was applied along detected grainline with length scale {length_scale:.6g} and width scale {width_scale:.6g}.",
                "warning",
            )
        ],
    )


def _scale_piece_along_grainline(
    piece: PolylineCandidate,
    length_scale: float,
    width_scale: float,
) -> tuple[tuple[float, float], ...]:
    assert piece.grainline_start is not None
    assert piece.grainline_end is not None
    dx = piece.grainline_end[0] - piece.grainline_start[0]
    dy = piece.grainline_end[1] - piece.grainline_start[1]
    length = hypot(dx, dy)
    if length <= 0:
        return piece.points
    ux = dx / length
    uy = dy / length
    vx = -uy
    vy = ux
    center_x = sum(point[0] for point in piece.points) / len(piece.points)
    center_y = sum(point[1] for point in piece.points) / len(piece.points)
    scaled: list[tuple[float, float]] = []
    for x, y in piece.points:
        rel_x = x - center_x
        rel_y = y - center_y
        along = rel_x * ux + rel_y * uy
        across = rel_x * vx + rel_y * vy
        scaled.append(
            (
                center_x + along * length_scale * ux + across * width_scale * vx,
                center_y + along * length_scale * uy + across * width_scale * vy,
            )
        )
    return tuple(scaled)


def _marker_yield_shrinkage(arguments: dict[str, Any]) -> dict[str, float]:
    configured = arguments.get("shrinkage")
    if isinstance(configured, dict):
        length = configured.get("length_percent", arguments.get("shrinkage_percent", 0))
        width = configured.get("width_percent", 0)
    else:
        length = arguments.get("shrinkage_percent", 0)
        width = 0
    return {
        "length_percent": float(length),
        "width_percent": float(width),
    }


def _resolved_csv_metadata_fields(piece_metadata: dict[str, PieceReportMetadata]) -> tuple[str, ...]:
    resolved: list[str] = []
    if piece_metadata and all(item.size is not None for item in piece_metadata.values()):
        resolved.append("size")
    if piece_metadata and all(item.quantity is not None for item in piece_metadata.values()):
        resolved.append("quantity")
    if piece_metadata and all(item.grainline_status is not None for item in piece_metadata.values()):
        resolved.append("grainline_status")
    if piece_metadata and all(item.piece_name is not None for item in piece_metadata.values()):
        resolved.append("piece_name")
    return tuple(resolved)


def _resolve_seam_allowance_width(seam_allowance: dict[str, Any], unit: str) -> float:
    from fattern.engine.metrics import default_seam_allowance_width

    if seam_allowance["status"] == "included":
        return 0.0
    fallback_width = seam_allowance.get("fallback_width")
    if isinstance(fallback_width, (int, float)) and not isinstance(fallback_width, bool) and fallback_width >= 0:
        return float(fallback_width)
    return default_seam_allowance_width(unit)


def _infer_marker_yield_grainline_status(extract_response: ToolResponse, grainline_required: bool) -> str:
    pieces = extract_response.get("piece_summary", [])
    if pieces and all(piece.get("has_grainline") is True for piece in pieces):
        return "present"
    return "missing" if grainline_required else "unknown"


def _marker_yield_one_way_fabric(nap_direction: str) -> bool | None:
    if nap_direction == "one_way":
        return True
    if nap_direction in {"two_way", "none", "no_nap", "not_one_way"}:
        return False
    return None


def _marker_yield_grainline_errors(arguments: dict[str, Any], grainline_status: str) -> list[dict[str, str]]:
    if grainline_status == "present":
        return []
    if arguments.get("nap_direction") == "one_way":
        return [
            _message(
                "MISSING_GRAINLINE_ON_ONE_WAY_FABRIC",
                "nap_direction=one_way requires grainline before calculating marker yield.",
                "blocker",
            )
        ]
    if arguments.get("grainline_required") is True:
        return [
            _message(
                "MISSING_GRAINLINE_REQUIRED",
                "Grainline is required before calculating marker yield.",
                "blocker",
            )
        ]
    if arguments.get("fabric_type") == "woven":
        return [
            _message(
                "MISSING_GRAINLINE_FOR_WOVEN",
                "fabric_type=woven requires grainline before calculating marker yield.",
                "blocker",
            )
        ]
    return []


def _has_blocker(response: ToolResponse) -> bool:
    return any(error.get("severity") == "blocker" for error in response.get("errors", []))


def _finalize_marker_yield(
    state: ToolResponse,
    stopped_at: str,
    errors: list[dict[str, str]],
) -> ToolResponse:
    response: ToolResponse = {
        "status": "blocked",
        "job_id": state["job_id"],
        "pattern_file_id": state["pattern_file_id"],
        "stopped_at": stopped_at,
        "tool_calls": list(state.get("tool_calls", [])),
        "warnings": list(state.get("warnings", [])),
        "errors": list(errors),
    }
    for key in ("dxf_parse_id", "piece_set_id", "metrics_id", "layout_id", "dxf_unit", "unit_scale", "layout"):
        if key in state:
            response[key] = state[key]

    result_artifact_id = None
    job_id = state.get("job_id")
    if isinstance(job_id, str):
        result_artifact_id = _register_result_json_artifact(
            state.get("store"),
            job_id,
            response,
        )
    if result_artifact_id is not None:
        response["artifact_ids"] = {"result_json": result_artifact_id}
        response["export_artifact_ids"] = [result_artifact_id]
        registry = state.get("registry")
        store = state.get("store")
        if isinstance(registry, McpToolRegistry) and isinstance(store, JobStore) and registry.persist_runs:
            response, _run = persist_run_outputs(
                store,
                response,
                source_name=str(state.get("source_name") or "blocked.dxf"),
                output_root=registry.output_root,
                web_base_url=registry.web_base_url,
            )
            store.get_artifact(job_id, result_artifact_id).path.write_text(
                json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
    return response


def _register_result_json_artifact(store: JobStore | None, job_id: str, response: ToolResponse) -> str | None:
    if store is None:
        return None
    result_artifact_id = store.register_artifact(
        job_id,
        "result.json",
        "{}",
        media_type="application/json",
    )
    store.get_artifact(job_id, result_artifact_id).path.write_text(
        json.dumps(
            {
                **response,
                "artifact_ids": {"result_json": result_artifact_id},
                "export_artifact_ids": [result_artifact_id],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return result_artifact_id


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


def _engine_warnings(warnings: list[dict[str, Any]]) -> tuple[EngineMessage, ...]:
    messages: list[EngineMessage] = []
    for warning in warnings:
        if warning.get("severity") != "warning":
            continue
        messages.append(
            EngineMessage(
                code=str(warning.get("code", "WARNING")),
                message=str(warning.get("message", "Warning")),
                severity="warning",
            )
        )
    return tuple(messages)


def _extend_unique_messages(target: list[dict[str, Any]], messages: list[dict[str, Any]]) -> None:
    seen = {
        (
            message.get("code"),
            message.get("message"),
            message.get("severity"),
        )
        for message in target
    }
    for message in messages:
        key = (
            message.get("code"),
            message.get("message"),
            message.get("severity"),
        )
        if key in seen:
            continue
        target.append(message)
        seen.add(key)


_UNIT_TO_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "inch": 25.4,
    "ft": 304.8,
    "yd": 914.4,
}


def _layout_result_in_mm(result: LayoutResult) -> LayoutResult:
    scale = _UNIT_TO_MM.get(result.unit, 1.0)
    area_scale = scale * scale
    placements = tuple(
        replace(
            placement,
            x=placement.x * scale,
            y=placement.y * scale,
            width=placement.width * scale,
            height=placement.height * scale,
        )
        for placement in result.placements
    )
    return replace(
        result,
        placements=placements,
        fabric_width=result.fabric_width * scale,
        marker_length=result.marker_length * scale,
        clearance=result.clearance * scale,
        unit="mm",
        total_piece_area=result.total_piece_area * area_scale,
    )


def _piece_metrics_in_mm(result: MetricsResult) -> dict[str, PieceMetrics]:
    converted: dict[str, PieceMetrics] = {}
    for metric in result.metrics:
        scale = _UNIT_TO_MM.get(metric.unit, 1.0)
        area_scale = scale * scale
        converted_metric = replace(
            metric,
            bbox=BoundingBox(
                min_x=metric.bbox.min_x * scale,
                min_y=metric.bbox.min_y * scale,
                max_x=metric.bbox.max_x * scale,
                max_y=metric.bbox.max_y * scale,
            ),
            area=metric.area * area_scale,
            perimeter=metric.perimeter * scale,
            unit="mm",
            points=tuple((point[0] * scale, point[1] * scale) for point in metric.points),
            seam_allowance_width=metric.seam_allowance_width * scale,
        )
        converted[metric.piece_id] = converted_metric
    return converted


def _excluded_report_ids(parse_result: Any) -> tuple[str, ...]:
    return tuple(f"entity_{item.source_entity_index:04d}" for item in parse_result.excluded_candidates)
