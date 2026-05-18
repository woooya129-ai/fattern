"""Command-line interface for the fattern package."""

from __future__ import annotations

import argparse
from base64 import b64encode
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from fattern.jobs import JobStore
from fattern.mcp import McpToolRegistry
from fattern.mcp.stdio import serve_stdio
from fattern.orchestration.intent import build_estimation_questionnaire
from fattern.runs import default_web_base_url, ensure_workspace_dirs, persist_run_outputs
from fattern.schemas import SUPPORTED_UNITS
from fattern.web import DEFAULT_HOST, DEFAULT_PORT, serve_web_ui


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) == 0:
        ensure_workspace_dirs()
        return serve_web_ui(host=DEFAULT_HOST, port=DEFAULT_PORT, open_browser=True)
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "estimate":
        return _estimate(args)
    if args.command == "questionnaire":
        return _questionnaire()
    if args.command == "mcp-stdio":
        return serve_stdio()
    if args.command == "ui":
        ensure_workspace_dirs()
        return serve_web_ui(host=args.host, port=args.port, open_browser=args.open_browser)
    if args.command == "host":
        ensure_workspace_dirs()
        try:
            return serve_web_ui(
                host=args.host,
                port=args.port,
                open_browser=args.open_browser,
                remote_mcp=True,
                remote_mcp_token=args.bearer_token or os.environ.get("FATTERN_REMOTE_MCP_TOKEN"),
                public_base_url=args.public_base_url or os.environ.get("FATTERN_PUBLIC_BASE_URL"),
                allowed_origins=tuple(args.allowed_origin or []),
            )
        except ValueError as exc:
            print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
            return 2
    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fattern", description="DXF rough marker yield estimator.")
    subparsers = parser.add_subparsers(dest="command")

    estimate = subparsers.add_parser("estimate", help="Estimate rough marker yield from a DXF file.")
    estimate.add_argument("dxf_file", type=Path, nargs="?", help="Input DXF file. Defaults to one DXF in input/.")
    estimate.add_argument("--input-dir", type=Path, default=Path("input"), help="Input directory. Default: input.")
    estimate.add_argument("--answers", type=Path, default=None, help="Questionnaire answer JSON. Default: input/answers.json if present.")
    estimate.add_argument("--fabric-width", type=float, default=None, help="Fabric width in the selected unit.")
    estimate.add_argument("--unit", choices=SUPPORTED_UNITS, default=None, help="Output and fabric width unit.")
    estimate.add_argument(
        "--dxf-unit",
        choices=("auto",),
        default=None,
        help="DXF coordinate unit handling. calculate_marker_yield currently supports auto only.",
    )
    estimate.add_argument(
        "--seam-allowance-included",
        choices=("yes", "no"),
        default=None,
        help="Whether seam allowance is already included in the pattern.",
    )
    estimate.add_argument(
        "--one-way-fabric",
        choices=("yes", "no"),
        default=None,
        help="Legacy alias for --nap-direction one_way/two_way.",
    )
    estimate.add_argument(
        "--grainline-required",
        choices=("yes", "no"),
        default=None,
        help="Whether grainline is required for this estimate.",
    )
    estimate.add_argument(
        "--nap-direction",
        choices=("one_way", "two_way", "none", "no_nap", "not_one_way", "unknown"),
        default=None,
        help="Fabric nap direction for the canonical marker request.",
    )
    estimate.add_argument("--rotation", "--allowed-rotation", dest="rotation", default=None, help="Comma-separated allowed rotations. Default: 0.")
    estimate.add_argument("--spacing", type=float, default=None, help="Minimum piece spacing in the selected unit. Default: 0.2.")
    estimate.add_argument("--clearance", type=float, default=None, help="Legacy alias for --spacing.")
    estimate.add_argument(
        "--fabric-type",
        choices=("woven", "knit", "unknown"),
        default=None,
        help="Fabric type for marker policy.",
    )
    estimate.add_argument("--shrinkage-percent", type=float, default=None, help="Length-direction shrinkage percent. Default: 0.")
    estimate.add_argument(
        "--seam-allowance-status",
        choices=("included", "excluded"),
        default=None,
        help="Canonical seam allowance status.",
    )
    estimate.add_argument(
        "--seam-allowance",
        type=float,
        default=None,
        help="Average seam allowance in the selected unit when seam allowance is not included.",
    )
    estimate.add_argument("--out", type=Path, default=Path("output"), help="Output directory. Default: output.")

    subparsers.add_parser("questionnaire", help="Print the setup questionnaire JSON.")
    subparsers.add_parser("mcp-stdio", help="Run the MCP server over stdio.")
    ui = subparsers.add_parser("ui", help="Run the local browser UI.")
    ui.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host. Default: {DEFAULT_HOST}.")
    ui.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Bind port. Default: {DEFAULT_PORT}.")
    ui.add_argument("--open-browser", action="store_true", help="Open the UI in the default browser.")
    host = subparsers.add_parser("host", help="Run hosted-prep Web UI with a remote MCP HTTP endpoint.")
    host.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host. Default: {DEFAULT_HOST}.")
    host.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Bind port. Default: {DEFAULT_PORT}.")
    host.add_argument("--open-browser", action="store_true", help="Open the UI in the default browser.")
    host.add_argument(
        "--bearer-token",
        default=None,
        help="Bearer token for /mcp. Defaults to FATTERN_REMOTE_MCP_TOKEN.",
    )
    host.add_argument(
        "--public-base-url",
        default=None,
        help="Public URL used in run links and server manifest. Defaults to FATTERN_PUBLIC_BASE_URL or request host.",
    )
    host.add_argument(
        "--allowed-origin",
        action="append",
        default=[],
        help="Allowed browser Origin for /mcp. Can be passed multiple times.",
    )
    return parser


def _questionnaire() -> int:
    print(json.dumps(build_estimation_questionnaire(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _estimate(args: argparse.Namespace) -> int:
    try:
        answers = _load_answers(args.answers, args.input_dir)
        request_answers = dict(answers)
        if args.nap_direction is not None:
            request_answers["nap_direction"] = args.nap_direction
        elif args.one_way_fabric is not None:
            request_answers["nap_direction"] = "one_way" if args.one_way_fabric == "yes" else "two_way"
        if args.fabric_type is not None:
            request_answers["fabric_type"] = args.fabric_type
        if args.shrinkage_percent is not None:
            request_answers["shrinkage_percent"] = args.shrinkage_percent
        if (
            args.seam_allowance_status is not None
            or args.seam_allowance_included is not None
            or args.seam_allowance is not None
        ):
            seam_allowance_status = args.seam_allowance_status
            if seam_allowance_status is None and args.seam_allowance_included is not None:
                seam_allowance_status = "included" if args.seam_allowance_included == "yes" else "excluded"
            if seam_allowance_status is None:
                seam_allowance_status = "excluded"
            seam_allowance_override: dict[str, Any] = {"status": seam_allowance_status}
            if args.seam_allowance is not None:
                seam_allowance_override["fallback_width"] = args.seam_allowance
            request_answers["seam_allowance"] = seam_allowance_override
        dxf_path = _resolve_dxf_path(args.dxf_file, args.input_dir)
        rotations = _parse_rotations(
            _answer_value(args.rotation, request_answers, "allowed_rotation", "rotation_allowed_degrees", "rotation") or "0"
        )
        fabric_width = _optional_float(_answer_value(args.fabric_width, request_answers, "fabric_width"))
        cuttable_width = _optional_float(_answer_value(None, request_answers, "cuttable_width"))
        unit = _optional_unit(_answer_value(args.unit, request_answers, "unit"))
        dxf_unit = _optional_dxf_unit(_answer_value(args.dxf_unit, request_answers, "dxf_unit_hint", "dxf_unit")) or "auto"
        spacing_cli = args.spacing if args.spacing is not None else args.clearance
        clearance = _optional_float(_answer_value(spacing_cli, request_answers, "spacing", "clearance"))
        seam_allowance = _optional_float(
            _answer_value(args.seam_allowance, request_answers, "seam_allowance_width")
        )
        seam_allowance_included = _optional_yes_no(
            _answer_value(args.seam_allowance_included, request_answers, "seam_allowance_included")
        )
        one_way_fabric = _optional_yes_no(_answer_value(args.one_way_fabric, request_answers, "one_way_fabric"))
        grainline_required = _optional_yes_no(_answer_value(args.grainline_required, request_answers, "grainline_required"))
        marker_request_options = _marker_request_options(
            request_answers,
            fabric_width=fabric_width,
            cuttable_width=cuttable_width,
            unit=unit,
            rotations=rotations,
            spacing=clearance,
            seam_allowance_included=seam_allowance_included,
            seam_allowance_width=seam_allowance,
            one_way_fabric=one_way_fabric,
            grainline_required=grainline_required,
        )
    except ValueError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    if dxf_unit != "auto":
        print(
            json.dumps(
                {
                    "status": "error",
                    "message": "dxf_unit_hint is not part of the calculate_marker_yield request contract.",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    if seam_allowance is not None and seam_allowance < 0:
        print(
            json.dumps({"status": "error", "message": "Seam allowance must be zero or greater."}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2

    store = JobStore()
    registry = McpToolRegistry(store, persist_runs=False)
    create_response = registry.call_tool(
        "create_job",
        {"schema_version": "1.0", "job_name": f"fattern:{dxf_path.stem}", "user_note": ""},
    )
    if _has_blocker(create_response):
        print(json.dumps(_public_result(create_response), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1

    register_response = registry.call_tool(
        "register_input_file",
        {
            "schema_version": "1.0",
            "job_id": create_response["job_id"],
            "file_name": dxf_path.name,
            "content_base64": b64encode(dxf_path.read_bytes()).decode("ascii"),
        },
    )
    if _has_blocker(register_response):
        print(json.dumps(_public_result(register_response), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1

    result = registry.call_tool(
        "calculate_marker_yield",
        _marker_yield_request(register_response["file_id"], marker_request_options),
    )
    if result.get("status") != "completed":
        print(json.dumps(_public_result(result), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1

    result, run = persist_run_outputs(
        store,
        result,
        source_name=dxf_path.name,
        output_root=args.out,
        web_base_url=default_web_base_url(),
    )
    response = _public_result(result)
    response["artifacts"] = {
        "svg": str(run.output_dir / "marker_preview.svg"),
        "report": str(run.output_dir / "marker_report.md"),
        "pdf": str(run.output_dir / "marker_report.pdf"),
        "csv": str(run.output_dir / "report.csv"),
        "result": str(run.output_dir / "result.json"),
        "summary": str(run.output_dir / "run_summary.txt"),
    }
    response["run_id"] = run.run_id
    response["output_dir"] = run.output_dir_display
    if run.web_url is not None:
        response["web_url"] = run.web_url
    if run.preview_url is not None:
        response["preview_url"] = run.preview_url
    if run.report_url is not None:
        response["report_url"] = run.report_url
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0


def _load_answers(answers_path: Path | None, input_dir: Path) -> dict[str, Any]:
    if answers_path is not None:
        path = answers_path
    else:
        candidates = [input_dir / "answers.json", input_dir.parent / "config" / "answers.json"]
        path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    if answers_path is None and not path.is_file():
        return {}
    if not path.is_file():
        raise ValueError("Questionnaire answer JSON was not found.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Questionnaire answer JSON is invalid.") from exc
    if not isinstance(data, dict):
        raise ValueError("Questionnaire answer JSON must be an object.")
    return data


def _resolve_dxf_path(dxf_file: Path | None, input_dir: Path) -> Path:
    if dxf_file is not None:
        path = dxf_file
        if not path.is_file():
            raise ValueError("DXF file was not found.")
        return path

    if not input_dir.is_dir():
        raise ValueError("Input directory was not found. Put one DXF in input/ or pass a DXF path.")
    candidates = sorted(path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() == ".dxf")
    if not candidates:
        raise ValueError("No DXF file was found in input/.")
    if len(candidates) > 1:
        raise ValueError("Multiple DXF files were found in input/. Pass the DXF path explicitly.")
    return candidates[0]


def _answer_value(cli_value: Any, answers: dict[str, Any], *keys: str) -> Any:
    if cli_value is not None:
        return cli_value
    for key in keys:
        if key in answers:
            return answers[key]
    return None


def _public_result(result: dict) -> dict:
    public = {
        "status": result.get("status", "blocked" if result.get("errors") else "error"),
        "stopped_at": result.get("stopped_at"),
        "warnings": result.get("warnings", []),
        "errors": result.get("errors", []),
    }
    if "layout" in result:
        public["layout"] = result["layout"]
    if "missing_fields" in result:
        public["missing_fields"] = result["missing_fields"]
    if "dxf_unit" in result:
        public["dxf_unit"] = result["dxf_unit"]
    if "unit_scale" in result:
        public["unit_scale"] = result["unit_scale"]
    return public


def _marker_request_options(
    answers: dict[str, Any],
    *,
    fabric_width: float | None,
    cuttable_width: float | None,
    unit: str | None,
    rotations: list[int],
    spacing: float | None,
    seam_allowance_included: bool | None,
    seam_allowance_width: float | None,
    one_way_fabric: bool | None,
    grainline_required: bool | None,
) -> dict[str, Any]:
    if fabric_width is None:
        raise ValueError("fabric_width is required.")
    if unit is None:
        raise ValueError("unit is required.")
    if cuttable_width is not None and cuttable_width > fabric_width:
        raise ValueError("cuttable_width must not be greater than fabric_width.")

    shrinkage_percent = _optional_float(answers.get("shrinkage_percent"))
    if shrinkage_percent is None:
        shrinkage_percent = 0.0
    if shrinkage_percent < 0:
        raise ValueError("shrinkage_percent must be zero or greater.")
    shrinkage = _optional_shrinkage(answers.get("shrinkage"))

    size_ratio = _optional_size_ratio(answers.get("size_ratio"))
    piece_quantity = _optional_piece_quantity(answers.get("piece_quantity"))
    fabric_type = _optional_fabric_type(answers.get("fabric_type"))
    stretch_direction = _optional_stretch_direction(answers.get("stretch_direction"))
    nap_direction = _optional_nap_direction(answers.get("nap_direction"))
    if nap_direction is None:
        nap_direction = _nap_direction_from_one_way_fabric(one_way_fabric)
    seam_allowance = _marker_yield_seam_allowance(
        answers.get("seam_allowance"),
        seam_allowance_included=seam_allowance_included,
        seam_allowance_width=seam_allowance_width,
    )
    if seam_allowance["status"] == "unknown":
        raise ValueError("seam_allowance.status is required and must be included or excluded.")

    return {
        "fabric_width": fabric_width,
        "cuttable_width": cuttable_width,
        "unit": unit,
        "size_ratio": size_ratio,
        "piece_quantity": piece_quantity,
        "spacing": spacing if spacing is not None else 0.2,
        "allowed_rotation": rotations,
        "grainline_required": True if grainline_required is None else grainline_required,
        "nap_direction": nap_direction,
        "shrinkage_percent": shrinkage_percent,
        "shrinkage": shrinkage,
        "fabric_type": fabric_type,
        "stretch_direction": stretch_direction,
        "seam_allowance": seam_allowance,
        "allowance_policy": answers.get("allowance_policy"),
    }


def _marker_yield_request(pattern_file_id: str, options: dict[str, Any]) -> dict[str, Any]:
    request = {
        "schema_version": "1.0",
        "pattern_file_id": pattern_file_id,
        **options,
    }
    if request.get("cuttable_width") is None:
        request.pop("cuttable_width")
    if request.get("shrinkage") is None:
        request.pop("shrinkage")
    if request.get("stretch_direction") is None:
        request.pop("stretch_direction")
    if request.get("allowance_policy") is None:
        request.pop("allowance_policy")
    return request


def _marker_yield_seam_allowance(
    canonical_value: Any,
    *,
    seam_allowance_included: bool | None,
    seam_allowance_width: float | None,
) -> dict[str, Any]:
    if isinstance(canonical_value, dict):
        status = str(canonical_value.get("status", "unknown")).strip().lower()
        if status in {"included", "excluded", "unknown"}:
            fallback_width = _optional_float(canonical_value.get("fallback_width"))
            result: dict[str, Any] = {"status": status}
            if fallback_width is not None:
                result["fallback_width"] = fallback_width
            return result

    if seam_allowance_included is True:
        return {"status": "included"}
    if seam_allowance_included is False:
        result = {"status": "excluded"}
        if seam_allowance_width is not None:
            result["fallback_width"] = seam_allowance_width
        return result
    return {"status": "unknown"}


def _optional_size_ratio(value: Any) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("size_ratio must be an object.")
    normalized: dict[str, int] = {}
    for size_name, quantity in value.items():
        if not isinstance(size_name, str) or not size_name.strip():
            raise ValueError("size_ratio keys must be non-empty strings.")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise ValueError("size_ratio quantities must be positive integers.")
        normalized[size_name] = quantity
    return normalized


def _optional_piece_quantity(value: Any) -> dict[str, int]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("piece_quantity must be an object.")
    normalized: dict[str, int] = {}
    for piece_id, quantity in value.items():
        if not isinstance(piece_id, str) or not piece_id.strip():
            raise ValueError("piece_quantity keys must be non-empty strings.")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise ValueError("piece_quantity values must be positive integers.")
        normalized[piece_id] = quantity
    return normalized


def _optional_shrinkage(value: Any) -> dict[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("shrinkage must be an object.")
    length = _optional_float(value.get("length_percent"))
    width = _optional_float(value.get("width_percent"))
    if length is None or width is None:
        raise ValueError("shrinkage must include length_percent and width_percent.")
    if length < 0 or width < 0:
        raise ValueError("shrinkage values must be zero or greater.")
    return {"length_percent": length, "width_percent": width}


def _optional_fabric_type(value: Any) -> str:
    if value is None:
        return "unknown"
    normalized = str(value).strip().lower()
    if normalized in {"woven", "knit", "unknown"}:
        return normalized
    raise ValueError("fabric_type must be woven, knit, or unknown.")


def _optional_stretch_direction(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"lengthwise", "crosswise", "bias", "unknown"}:
        return normalized
    raise ValueError("stretch_direction must be lengthwise, crosswise, bias, or unknown.")


def _optional_nap_direction(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"one_way", "two_way", "none", "no_nap", "not_one_way", "unknown"}:
        return normalized
    raise ValueError("nap_direction is not supported.")


def _nap_direction_from_one_way_fabric(value: bool | None) -> str:
    if value is True:
        return "one_way"
    if value is False:
        return "two_way"
    return "unknown"


def _has_blocker(response: dict[str, Any]) -> bool:
    return any(error.get("severity") == "blocker" for error in response.get("errors", []))


def _parse_rotations(value: str | list[int] | tuple[int, ...]) -> list[int]:
    rotations: list[int] = []
    items = value if isinstance(value, (list, tuple)) else value.split(",")
    for item in items:
        text = str(item).strip()
        if not text:
            continue
        try:
            rotation = int(text)
        except ValueError as exc:
            raise ValueError("Rotation must be a comma-separated list of integers.") from exc
        if rotation not in {0, 90, 180, 270}:
            raise ValueError("Rotation must use only 0, 90, 180, 270.")
        if rotation not in rotations:
            rotations.append(rotation)
    if not rotations:
        raise ValueError("At least one rotation is required.")
    return rotations


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Number fields must be numeric.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Number fields must be numeric.") from exc


def _optional_unit(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in SUPPORTED_UNITS:
        return normalized
    return None


def _optional_dxf_unit(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized == "auto" or normalized in SUPPORTED_UNITS:
        return normalized
    return "auto"


def _optional_yes_no(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"yes", "y", "true", "1"}:
        return True
    if normalized in {"no", "n", "false", "0"}:
        return False
    return None


if __name__ == "__main__":
    raise SystemExit(main())
