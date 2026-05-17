"""Command-line interface for the fattern package."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence

from fattern.jobs import JobStore
from fattern.mcp import McpToolRegistry
from fattern.mcp.stdio import serve_stdio
from fattern.orchestration.chain import execute_marker_estimation
from fattern.orchestration.intent import build_estimation_questionnaire, normalize_user_intent
from fattern.schemas import SUPPORTED_UNITS


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "estimate":
        return _estimate(args)
    if args.command == "questionnaire":
        return _questionnaire()
    if args.command == "mcp-stdio":
        return serve_stdio()
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
        choices=("auto", *SUPPORTED_UNITS),
        default=None,
        help="DXF coordinate unit hint. Default: auto.",
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
        help="Whether the fabric is one-way directional fabric.",
    )
    estimate.add_argument(
        "--grainline-status",
        choices=("present", "missing", "unknown"),
        default=None,
        help="Whether grainline is present in the DXF. Default: unknown.",
    )
    estimate.add_argument("--rotation", default=None, help="Comma-separated allowed rotations. Default: 0.")
    estimate.add_argument("--clearance", type=float, default=None, help="Piece clearance. Default: 0.2.")
    estimate.add_argument(
        "--seam-allowance",
        type=float,
        default=None,
        help="Average seam allowance in the selected unit when seam allowance is not included.",
    )
    estimate.add_argument("--out", type=Path, default=Path("output"), help="Output directory. Default: output.")

    subparsers.add_parser("questionnaire", help="Print the setup questionnaire JSON.")
    subparsers.add_parser("mcp-stdio", help="Run the MCP server over stdio.")
    return parser


def _questionnaire() -> int:
    print(json.dumps(build_estimation_questionnaire(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _estimate(args: argparse.Namespace) -> int:
    try:
        answers = _load_answers(args.answers, args.input_dir)
        dxf_path = _resolve_dxf_path(args.dxf_file, args.input_dir)
        rotations = _parse_rotations(_answer_value(args.rotation, answers, "rotation_allowed_degrees", "rotation") or "0")
        fabric_width = _optional_float(_answer_value(args.fabric_width, answers, "fabric_width"))
        unit = _optional_unit(_answer_value(args.unit, answers, "unit"))
        dxf_unit = _optional_dxf_unit(_answer_value(args.dxf_unit, answers, "dxf_unit_hint", "dxf_unit")) or "auto"
        clearance = _optional_float(_answer_value(args.clearance, answers, "clearance"))
        seam_allowance = _optional_float(
            _answer_value(args.seam_allowance, answers, "seam_allowance_width", "seam_allowance")
        )
        seam_allowance_included = _optional_yes_no(
            _answer_value(args.seam_allowance_included, answers, "seam_allowance_included")
        )
        one_way_fabric = _optional_yes_no(_answer_value(args.one_way_fabric, answers, "one_way_fabric"))
        grainline_status = _optional_grainline_status(_answer_value(args.grainline_status, answers, "grainline_status"))
    except ValueError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    if seam_allowance is not None and seam_allowance < 0:
        print(
            json.dumps({"status": "error", "message": "Seam allowance must be zero or greater."}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2

    user_intent = normalize_user_intent(
        {
            "dxf_file": dxf_path.name,
            "unit": unit,
            "dxf_unit_hint": dxf_unit,
            "fabric_width": fabric_width,
            "rules": {
                "seam_allowance_included": seam_allowance_included,
                "seam_allowance_width": seam_allowance,
                "one_way_fabric": one_way_fabric,
                "grainline_status": grainline_status,
                "rotation_allowed_degrees": rotations,
                "clearance": clearance,
            },
        }
    )

    store = JobStore()
    registry = McpToolRegistry(store)
    result = execute_marker_estimation(
        user_intent,
        dxf_file_name=dxf_path.name,
        dxf_content=dxf_path.read_bytes(),
        registry=registry,
        job_name=f"fattern:{dxf_path.stem}",
    )
    if result["status"] != "completed":
        print(json.dumps(_public_result(result), ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1

    output_dir = _create_run_output_dir(args.out, dxf_path)
    written = _copy_artifacts(store, result, output_dir)
    response = _public_result(result)
    response["artifacts"] = {name: str(path) for name, path in written.items()}
    result_path = output_dir / "result.json"
    response["artifacts"]["result"] = str(result_path)
    response["output_dir"] = str(output_dir)
    result_path.write_text(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0


def _load_answers(answers_path: Path | None, input_dir: Path) -> dict[str, Any]:
    path = answers_path or input_dir / "answers.json"
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


def _copy_artifacts(store: JobStore, result: dict, output_dir: Path) -> dict[str, Path]:
    artifact_ids = {
        "svg": result["svg_artifact_id"],
        "report": result["report_artifact_id"],
    }
    written: dict[str, Path] = {}
    for name, artifact_id in artifact_ids.items():
        artifact = store.get_artifact(result["job_id"], artifact_id)
        destination = output_dir / artifact.file_name
        shutil.copyfile(artifact.path, destination)
        written[name] = destination
    return written


def _create_run_output_dir(output_root: Path, dxf_path: Path) -> Path:
    safe_stem = _safe_output_name(dxf_path.stem)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = output_root / f"{timestamp}_{safe_stem}"
    candidate = base
    suffix = 2
    while candidate.exists():
        candidate = output_root / f"{timestamp}_{safe_stem}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _safe_output_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return cleaned[:80] or "dxf"


def _public_result(result: dict) -> dict:
    public = {
        "status": result["status"],
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


def _optional_grainline_status(value: Any) -> str:
    if value is None:
        return "unknown"
    normalized = str(value).strip().lower()
    if normalized in {"present", "missing", "unknown"}:
        return normalized
    return "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
