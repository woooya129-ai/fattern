"""In-memory job workspace store for MCP tool wrappers."""

from __future__ import annotations

import secrets
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from fattern.engine import DxfParseResult, LayoutResult, MetricsResult, PolylineCandidate

from .security import (
    ALLOWED_ARTIFACT_SUFFIXES,
    ALLOWED_INPUT_SUFFIXES,
    SecurityError,
    resolve_workspace_file,
    validate_artifact_filename,
    validate_input_filename,
    validate_opaque_id,
)

DEFAULT_MAX_ARTIFACT_BYTES = 10 * 1024 * 1024


class JobError(ValueError):
    """Raised when an opaque ID cannot be resolved in the server mapping."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


@dataclass
class FileRecord:
    file_id: str
    path: Path
    original_name: str


@dataclass
class ArtifactRecord:
    artifact_id: str
    path: Path
    file_name: str
    media_type: str
    exportable: bool = True


@dataclass
class JobRecord:
    job_id: str
    workspace_root: Path
    job_name: str
    user_note: str
    created_at: datetime
    files: dict[str, FileRecord | Path] = field(default_factory=dict)
    dxf_parses: dict[str, DxfParseResult] = field(default_factory=dict)
    piece_sets: dict[str, tuple[PolylineCandidate, ...]] = field(default_factory=dict)
    metrics: dict[str, MetricsResult] = field(default_factory=dict)
    layouts: dict[str, LayoutResult] = field(default_factory=dict)
    artifacts: dict[str, ArtifactRecord] = field(default_factory=dict)


class JobStore:
    """Server-side mapping from opaque IDs to isolated job workspaces."""

    def __init__(self, root: Path | str | None = None) -> None:
        base = Path(root) if root is not None else Path(tempfile.gettempdir()) / "fattern-jobs"
        base.mkdir(parents=True, exist_ok=True)
        self._root = base.resolve(strict=True)
        self._jobs: dict[str, JobRecord] = {}

    @property
    def root(self) -> Path:
        return self._root

    def create_job(self, job_name: str, user_note: str = "") -> JobRecord:
        job_id = self._new_id("job")
        workspace_root = self._root / job_id
        (workspace_root / "inputs").mkdir(parents=True, exist_ok=False)
        (workspace_root / "objects").mkdir(parents=True, exist_ok=True)
        (workspace_root / "artifacts").mkdir(parents=True, exist_ok=True)
        (workspace_root / "logs").mkdir(parents=True, exist_ok=True)

        record = JobRecord(
            job_id=job_id,
            workspace_root=workspace_root.resolve(strict=True),
            job_name=_safe_text(job_name, max_length=120),
            user_note=_safe_text(user_note, max_length=500),
            created_at=datetime.now(UTC),
        )
        self._jobs[job_id] = record
        return record

    def get_job(self, job_id: object) -> JobRecord:
        safe_id = validate_opaque_id(job_id)
        record = self._jobs.get(safe_id)
        if record is None:
            raise JobError("JOB_NOT_FOUND", "Job was not found.")
        return record

    def require_job(self, job_id: object) -> JobRecord:
        return self.get_job(job_id)

    def register_input_file(self, job_id: object, file_name: object, content: bytes | str) -> str:
        record = self.get_job(job_id)
        safe_name = validate_input_filename(file_name)
        suffix = Path(safe_name).suffix.lower()
        file_id = self._new_id("file")
        internal_path = record.workspace_root / "inputs" / f"{file_id}{suffix}"
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        internal_path.write_bytes(data)
        canonical_path = resolve_workspace_file(record.workspace_root, internal_path, allowed_suffixes=ALLOWED_INPUT_SUFFIXES)
        record.files[file_id] = FileRecord(file_id=file_id, path=canonical_path, original_name=safe_name)
        return file_id

    def register_file_text(self, job_id: object, content: str, file_name: object) -> str:
        return self.register_input_file(job_id, file_name, content)

    def get_file_path(self, job_id: object, file_id: object) -> Path:
        record = self.get_job(job_id)
        safe_file_id = validate_opaque_id(file_id)
        file_record = record.files.get(safe_file_id)
        if file_record is None:
            raise JobError("FILE_NOT_FOUND", "File was not found.")
        mapped_path = file_record.path if isinstance(file_record, FileRecord) else file_record
        return resolve_workspace_file(record.workspace_root, mapped_path, allowed_suffixes=ALLOWED_INPUT_SUFFIXES)

    def store_dxf_parse(self, job_id: object, result: DxfParseResult) -> str:
        record = self.get_job(job_id)
        dxf_parse_id = self._new_id("dxf_parse")
        record.dxf_parses[dxf_parse_id] = result
        return dxf_parse_id

    def get_dxf_parse(self, job_id: object, dxf_parse_id: object) -> DxfParseResult:
        record = self.get_job(job_id)
        safe_id = validate_opaque_id(dxf_parse_id)
        result = record.dxf_parses.get(safe_id)
        if result is None:
            raise JobError("DXF_PARSE_NOT_FOUND", "DXF parse result was not found.")
        return result

    def store_piece_set(self, job_id: object, pieces: tuple[PolylineCandidate, ...]) -> str:
        record = self.get_job(job_id)
        piece_set_id = self._new_id("piece_set")
        record.piece_sets[piece_set_id] = pieces
        return piece_set_id

    def get_piece_set(self, job_id: object, piece_set_id: object) -> tuple[PolylineCandidate, ...]:
        record = self.get_job(job_id)
        safe_id = validate_opaque_id(piece_set_id)
        pieces = record.piece_sets.get(safe_id)
        if pieces is None:
            raise JobError("PIECE_SET_NOT_FOUND", "Piece set was not found.")
        return pieces

    def store_metrics(self, job_id: object, result: MetricsResult) -> str:
        record = self.get_job(job_id)
        metrics_id = self._new_id("metrics")
        record.metrics[metrics_id] = result
        return metrics_id

    def get_metrics(self, job_id: object, metrics_id: object) -> MetricsResult:
        record = self.get_job(job_id)
        safe_id = validate_opaque_id(metrics_id)
        result = record.metrics.get(safe_id)
        if result is None:
            raise JobError("METRICS_NOT_FOUND", "Metrics result was not found.")
        return result

    def store_layout(self, job_id: object, result: LayoutResult) -> str:
        record = self.get_job(job_id)
        layout_id = self._new_id("layout")
        record.layouts[layout_id] = result
        return layout_id

    def get_layout(self, job_id: object, layout_id: object) -> LayoutResult:
        record = self.get_job(job_id)
        safe_id = validate_opaque_id(layout_id)
        result = record.layouts.get(safe_id)
        if result is None:
            raise JobError("LAYOUT_NOT_FOUND", "Layout result was not found.")
        return result

    def register_artifact(
        self,
        job_id: object,
        file_name: object,
        content: bytes | str,
        *,
        media_type: str = "application/octet-stream",
        exportable: bool = True,
        max_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
    ) -> str:
        record = self.get_job(job_id)
        safe_name = validate_artifact_filename(file_name)
        suffix = Path(safe_name).suffix.lower()
        artifact_id = self._new_id("artifact")
        internal_path = record.workspace_root / "artifacts" / f"{artifact_id}{suffix}"
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        if max_bytes <= 0 or len(data) > max_bytes:
            raise SecurityError("ARTIFACT_SIZE_LIMIT_EXCEEDED", "Artifact exceeds the configured size limit.")
        internal_path.write_bytes(data)
        canonical_path = self._resolve_artifact_path(record, internal_path)
        record.artifacts[artifact_id] = ArtifactRecord(
            artifact_id=artifact_id,
            path=canonical_path,
            file_name=safe_name,
            media_type=_safe_text(media_type, max_length=120),
            exportable=exportable,
        )
        return artifact_id

    def get_artifact(self, job_id: object, artifact_id: object) -> ArtifactRecord:
        record = self.get_job(job_id)
        artifact = self._get_artifact_record(record, artifact_id)
        self._resolve_artifact_path(record, artifact.path)
        return artifact

    def export_artifacts_zip(self, job_id: object, artifact_ids: list[object] | tuple[object, ...]) -> str:
        record = self.get_job(job_id)
        artifacts = [self._get_exportable_artifact(record, artifact_id) for artifact_id in artifact_ids]
        archive_id = self._new_id("artifact")
        archive_path = record.workspace_root / "artifacts" / f"{archive_id}.zip"

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            used_entry_names: set[str] = set()
            for artifact in artifacts:
                source_path = self._resolve_artifact_path(record, artifact.path)
                entry_name = _zip_entry_name(artifact)
                if entry_name in used_entry_names:
                    entry_name = f"{artifact.artifact_id}_{entry_name}"
                _assert_safe_zip_entry(entry_name)
                archive.write(source_path, arcname=entry_name)
                used_entry_names.add(entry_name)

        _validate_zip_entries(archive_path)
        if archive_path.stat().st_size > DEFAULT_MAX_ARTIFACT_BYTES:
            try:
                archive_path.unlink()
            except OSError:
                pass
            raise SecurityError("ARTIFACT_SIZE_LIMIT_EXCEEDED", "Artifact exceeds the configured size limit.")
        canonical_path = self._resolve_artifact_path(record, archive_path, allowed_suffixes=frozenset({".zip"}))
        record.artifacts[archive_id] = ArtifactRecord(
            artifact_id=archive_id,
            path=canonical_path,
            file_name=f"{archive_id}.zip",
            media_type="application/zip",
            exportable=False,
        )
        return archive_id

    def _get_artifact_record(self, record: JobRecord, artifact_id: object) -> ArtifactRecord:
        safe_id = validate_opaque_id(artifact_id)
        artifact = record.artifacts.get(safe_id)
        if artifact is None:
            raise JobError("ARTIFACT_NOT_FOUND", "Artifact was not found.")
        return artifact

    def _get_exportable_artifact(self, record: JobRecord, artifact_id: object) -> ArtifactRecord:
        artifact = self._get_artifact_record(record, artifact_id)
        if not artifact.exportable:
            raise JobError("ARTIFACT_NOT_EXPORTABLE", "Artifact is not exportable.")
        validate_artifact_filename(artifact.file_name)
        self._resolve_artifact_path(record, artifact.path)
        return artifact

    def _resolve_artifact_path(
        self,
        record: JobRecord,
        candidate: Path,
        *,
        allowed_suffixes: frozenset[str] = ALLOWED_ARTIFACT_SUFFIXES,
    ) -> Path:
        resolved = resolve_workspace_file(record.workspace_root, candidate, allowed_suffixes=allowed_suffixes)
        artifacts_root = (record.workspace_root / "artifacts").resolve(strict=True)
        if not resolved.is_relative_to(artifacts_root):
            raise SecurityError("PATH_CONTAINMENT_FAILED", "Artifact failed workspace containment checks.")
        return resolved

    def _new_id(self, prefix: str) -> str:
        for _ in range(20):
            candidate = f"{prefix}_{secrets.token_hex(8)}"
            if candidate not in self._ids_for_prefix(prefix):
                return candidate
        raise JobError("ID_GENERATION_FAILED", "Could not allocate an opaque ID.")

    def _ids_for_prefix(self, prefix: str) -> set[str]:
        ids: set[str] = set()
        for record in self._jobs.values():
            if prefix == "job":
                ids.add(record.job_id)
            elif prefix == "file":
                ids.update(record.files)
            elif prefix == "dxf_parse":
                ids.update(record.dxf_parses)
            elif prefix == "piece_set":
                ids.update(record.piece_sets)
            elif prefix == "metrics":
                ids.update(record.metrics)
            elif prefix == "layout":
                ids.update(record.layouts)
            elif prefix == "artifact":
                ids.update(record.artifacts)
        return ids


def _zip_entry_name(artifact: ArtifactRecord) -> str:
    safe_name = validate_artifact_filename(artifact.file_name)
    entry_name = f"{artifact.artifact_id}_{safe_name}"
    _assert_safe_zip_entry(entry_name)
    return entry_name


def _assert_safe_zip_entry(entry_name: str) -> None:
    path = PurePosixPath(entry_name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise SecurityError("ZIP_SLIP_BLOCKED", "Archive entry failed security checks.")


def _validate_zip_entries(archive_path: Path) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for name in archive.namelist():
                _assert_safe_zip_entry(name)
    except zipfile.BadZipFile as exc:
        raise SecurityError("ZIP_CREATION_FAILED", "Archive creation failed security checks.") from exc


def _safe_text(value: str, *, max_length: int) -> str:
    clean = "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in str(value)).strip()
    return clean[:max_length]
