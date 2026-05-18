"""Shared workspace and run artifact helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
from typing import Any

from fattern.jobs import JobStore


DEFAULT_WEB_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_OUTPUT_ROOT = Path("output")
WORKSPACE_DIRS = ("input", "output", "config")

ARTIFACT_KEY_TO_NAME = {
    "marker_preview_svg": "marker_preview.svg",
    "marker_report_md": "marker_report.md",
    "marker_report_pdf": "marker_report.pdf",
    "report_csv": "report.csv",
}

RUN_FILE_NAMES = frozenset(
    {
        "marker_preview.svg",
        "marker_report.md",
        "marker_report.pdf",
        "report.csv",
        "result.json",
        "run_summary.txt",
    }
)


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    output_dir: Path
    output_dir_display: str
    web_url: str | None
    preview_url: str | None
    report_url: str | None
    files: tuple[str, ...]


def ensure_workspace_dirs(root: Path | str = ".") -> None:
    base = Path(root)
    for name in WORKSPACE_DIRS:
        (base / name).mkdir(parents=True, exist_ok=True)
    answers_path = base / "config" / "answers.json"
    if not answers_path.exists():
        answers_path.write_text(_default_answers_json(), encoding="utf-8")


def default_web_base_url() -> str:
    return os.environ.get("FATTERN_WEB_BASE_URL", DEFAULT_WEB_BASE_URL).rstrip("/")


def default_output_root() -> Path:
    return Path(os.environ.get("FATTERN_OUTPUT_DIR", str(DEFAULT_OUTPUT_ROOT)))


def persist_run_outputs(
    store: JobStore,
    result: dict[str, Any],
    *,
    source_name: str,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    web_base_url: str | None = DEFAULT_WEB_BASE_URL,
) -> tuple[dict[str, Any], RunRecord]:
    """Copy exportable artifacts into output/run_id and attach run URLs."""

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    run_id = _unique_run_id(root, source_name)
    output_dir = root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)

    copied: list[str] = []
    artifact_ids = result.get("artifact_ids", {})
    if isinstance(artifact_ids, dict):
        for key, file_name in ARTIFACT_KEY_TO_NAME.items():
            artifact_id = artifact_ids.get(key)
            if not isinstance(artifact_id, str):
                continue
            artifact = store.get_artifact(result["job_id"], artifact_id)
            shutil.copyfile(artifact.path, output_dir / file_name)
            copied.append(file_name)

    run_urls = _run_urls(run_id, web_base_url)
    run_record = RunRecord(
        run_id=run_id,
        output_dir=output_dir,
        output_dir_display=_display_path(output_dir),
        web_url=run_urls["web_url"],
        preview_url=run_urls["preview_url"] if (output_dir / "marker_preview.svg").is_file() else None,
        report_url=run_urls["report_url"] if (output_dir / "marker_report.pdf").is_file() else None,
        files=tuple(sorted({*copied, "result.json", "run_summary.txt"})),
    )
    enriched = attach_run_metadata(result, run_record)
    (output_dir / "result.json").write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "run_summary.txt").write_text(render_run_summary(enriched), encoding="utf-8")
    return enriched, run_record


def attach_run_metadata(result: dict[str, Any], run_record: RunRecord) -> dict[str, Any]:
    enriched = dict(result)
    enriched["run_id"] = run_record.run_id
    enriched["output_dir"] = run_record.output_dir_display
    if run_record.web_url is not None:
        enriched["web_url"] = run_record.web_url
    if run_record.preview_url is not None:
        enriched["preview_url"] = run_record.preview_url
    if run_record.report_url is not None:
        enriched["report_url"] = run_record.report_url
    enriched["run_files"] = list(run_record.files)
    return enriched


def load_run_result(run_id: str, output_root: Path | str = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    output_dir = resolve_run_dir(run_id, output_root)
    return json.loads((output_dir / "result.json").read_text(encoding="utf-8"))


def resolve_run_dir(run_id: str, output_root: Path | str = DEFAULT_OUTPUT_ROOT) -> Path:
    if not _safe_run_id(run_id):
        raise ValueError("Invalid run_id.")
    root = Path(output_root).resolve()
    output_dir = (root / run_id).resolve()
    if not output_dir.is_relative_to(root) or not output_dir.is_dir():
        raise ValueError("Run was not found.")
    return output_dir


def resolve_run_file(run_id: str, file_name: str, output_root: Path | str = DEFAULT_OUTPUT_ROOT) -> Path:
    if file_name not in RUN_FILE_NAMES:
        raise ValueError("Run file is not exportable.")
    output_dir = resolve_run_dir(run_id, output_root)
    path = (output_dir / file_name).resolve()
    if not path.is_relative_to(output_dir) or not path.is_file():
        raise ValueError("Run file was not found.")
    return path


def render_run_summary(result: dict[str, Any]) -> str:
    lines = [
        "Fattern run summary",
        "",
        f"status: {result.get('status', 'unknown')}",
        f"run_id: {result.get('run_id', 'n/a')}",
    ]
    minimum = _yield_line("minimum_yield", result.get("minimum_yield"), "marker_length")
    quote = _yield_line("quote_yield", result.get("quote_yield"), "final_yield")
    if minimum:
        lines.append(minimum)
    if quote:
        lines.append(quote)
    confidence = result.get("confidence")
    if isinstance(confidence, dict):
        lines.append(f"confidence: {confidence.get('grade', 'unknown')}")
    if result.get("web_url"):
        lines.append(f"web_url: {result['web_url']}")
    if result.get("preview_url"):
        lines.append(f"preview_url: {result['preview_url']}")
    if result.get("report_url"):
        lines.append(f"report_url: {result['report_url']}")

    warnings = result.get("warnings") or []
    errors = result.get("errors") or []
    if errors:
        lines.extend(["", "errors:"])
        lines.extend(f"- {item.get('code')}: {item.get('message')}" for item in errors)
    if warnings:
        lines.extend(["", "warnings:"])
        lines.extend(f"- {item.get('code')}: {item.get('message')}" for item in warnings)
    lines.extend(
        [
            "",
            "note: quote_yield is a quotation estimate, not a production-confirmed marker yield.",
            "",
        ]
    )
    return "\n".join(lines)


def _yield_line(label: str, value: object, field: str) -> str:
    if not isinstance(value, dict):
        return ""
    amount = value.get(field)
    unit = value.get("unit") or value.get("policy_unit") or ""
    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        return ""
    text = f"{amount:.6f}".rstrip("0").rstrip(".")
    return f"{label}: {text} {unit}".strip()


def _unique_run_id(output_root: Path, source_name: str) -> str:
    safe_stem = _safe_output_name(Path(source_name or "dxf").stem)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{timestamp}_{safe_stem}"
    candidate = base
    suffix = 2
    while (output_root / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _safe_output_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return cleaned[:80] or "dxf"


def _safe_run_id(value: str) -> bool:
    return bool(value) and all(char.isalnum() or char in {"-", "_"} for char in value)


def _display_path(path: Path) -> str:
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return str(path)


def _run_urls(run_id: str, web_base_url: str | None) -> dict[str, str | None]:
    if not web_base_url:
        return {"web_url": None, "preview_url": None, "report_url": None}
    base = web_base_url.rstrip("/")
    return {
        "web_url": f"{base}/runs/{run_id}",
        "preview_url": f"{base}/runs/{run_id}/marker_preview.svg",
        "report_url": f"{base}/runs/{run_id}/marker_report.pdf",
    }


def _default_answers_json() -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "fabric_width": 150,
            "unit": "cm",
            "size_ratio": {},
            "spacing": 0.2,
            "allowed_rotation": [0],
            "grainline_required": False,
            "nap_direction": "two_way",
            "shrinkage_percent": 0,
            "fabric_type": "unknown",
            "seam_allowance": {"status": "included"},
            "allowance_policy": {"mode": "fast_quote"},
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
