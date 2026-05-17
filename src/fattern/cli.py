"""Command-line interface for the fattern package."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Sequence

from fattern.jobs import JobStore
from fattern.mcp import McpToolRegistry
from fattern.orchestration.chain import execute_marker_estimation
from fattern.orchestration.intent import normalize_user_intent


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "estimate":
        return _estimate(args)
    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fattern", description="DXF rough marker yield estimator.")
    subparsers = parser.add_subparsers(dest="command")

    estimate = subparsers.add_parser("estimate", help="Estimate rough marker yield from a DXF file.")
    estimate.add_argument("dxf_file", type=Path, help="Input DXF file.")
    estimate.add_argument("--fabric-width", type=float, required=True, help="Fabric width in the selected unit.")
    estimate.add_argument("--unit", choices=("mm", "cm", "inch"), required=True, help="DXF and fabric width unit.")
    estimate.add_argument(
        "--seam-allowance-included",
        choices=("yes", "no"),
        required=True,
        help="Whether seam allowance is already included in the pattern.",
    )
    estimate.add_argument(
        "--one-way-fabric",
        choices=("yes", "no"),
        required=True,
        help="Whether the fabric is one-way directional fabric.",
    )
    estimate.add_argument("--rotation", default="0,180", help="Comma-separated allowed rotations. Default: 0,180.")
    estimate.add_argument("--clearance", type=float, default=0.2, help="Piece clearance. Default: 0.2.")
    estimate.add_argument("--out", type=Path, default=Path("fattern-output"), help="Output directory.")
    return parser


def _estimate(args: argparse.Namespace) -> int:
    dxf_path = args.dxf_file
    if not dxf_path.is_file():
        print(json.dumps({"status": "error", "message": "DXF file was not found."}, ensure_ascii=False), file=sys.stderr)
        return 2

    try:
        rotations = _parse_rotations(args.rotation)
    except ValueError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    user_intent = normalize_user_intent(
        {
            "dxf_file": dxf_path.name,
            "unit": args.unit,
            "fabric_width": args.fabric_width,
            "rules": {
                "seam_allowance_included": _yes_no(args.seam_allowance_included),
                "one_way_fabric": _yes_no(args.one_way_fabric),
                "rotation_allowed_degrees": rotations,
                "clearance": args.clearance,
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

    output_dir = args.out
    output_dir.mkdir(parents=True, exist_ok=True)
    written = _copy_artifacts(store, result, output_dir)
    response = _public_result(result)
    response["artifacts"] = {name: str(path) for name, path in written.items()}
    print(json.dumps(response, ensure_ascii=False, sort_keys=True))
    return 0


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


def _public_result(result: dict) -> dict:
    public = {
        "status": result["status"],
        "stopped_at": result.get("stopped_at"),
        "warnings": result.get("warnings", []),
        "errors": result.get("errors", []),
    }
    if "layout" in result:
        public["layout"] = result["layout"]
    return public


def _parse_rotations(value: str) -> list[int]:
    rotations: list[int] = []
    for item in value.split(","):
        text = item.strip()
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


def _yes_no(value: str) -> bool:
    return value == "yes"


if __name__ == "__main__":
    raise SystemExit(main())
