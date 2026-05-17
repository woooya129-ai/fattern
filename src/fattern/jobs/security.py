"""Security helpers for ID-based job workspace access."""

from __future__ import annotations

import re
import stat
from pathlib import Path
from typing import Iterable

from fattern.schemas import ID_PATTERN

ALLOWED_INPUT_SUFFIXES = frozenset({".dxf", ".json"})
ALLOWED_ARTIFACT_SUFFIXES = frozenset({".json", ".md", ".svg", ".csv", ".pdf", ".zip"})
OPAQUE_ID_RE = re.compile(ID_PATTERN)


class SecurityError(ValueError):
    """Raised when an internal file reference violates workspace policy."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.public_message = message


def validate_opaque_id(value: object) -> str:
    if not isinstance(value, str) or OPAQUE_ID_RE.fullmatch(value) is None:
        raise SecurityError("INVALID_OPAQUE_ID", "Identifier failed opaque ID validation.")
    return value


def validate_input_filename(value: object) -> str:
    name = _validate_plain_filename(value)
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_INPUT_SUFFIXES:
        raise SecurityError("UNSUPPORTED_FILE_TYPE", "Input file type is not allowed.")
    return name


def validate_artifact_filename(value: object) -> str:
    name = _validate_plain_filename(value)
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_ARTIFACT_SUFFIXES:
        raise SecurityError("UNSUPPORTED_ARTIFACT_TYPE", "Artifact file type is not allowed.")
    return name


def _validate_plain_filename(value: object) -> str:
    if not isinstance(value, str):
        raise SecurityError("INVALID_FILE_NAME", "File name failed validation.")

    name = value.strip()
    if not name or name in {".", ".."}:
        raise SecurityError("INVALID_FILE_NAME", "File name failed validation.")
    if _contains_control_char(name):
        raise SecurityError("INVALID_FILE_NAME", "File name failed validation.")
    if _looks_like_uri(name) or _is_unc_token(name) or _has_drive_letter(name):
        raise SecurityError("INVALID_FILE_NAME", "File name failed validation.")
    if "/" in name or "\\" in name or ":" in name:
        raise SecurityError("INVALID_FILE_NAME", "File name failed validation.")
    if Path(name).name != name:
        raise SecurityError("INVALID_FILE_NAME", "File name failed validation.")
    return name


def resolve_workspace_file(
    workspace_root: Path,
    candidate: Path,
    *,
    allowed_suffixes: Iterable[str] = ALLOWED_INPUT_SUFFIXES,
    require_file: bool = True,
) -> Path:
    """Return a canonical path after enforcing job workspace containment.

    The caller may pass an internal absolute path from the server mapping. User
    tool input is never passed here as a path.
    """

    root = workspace_root.resolve(strict=True)
    path = candidate if candidate.is_absolute() else root / candidate
    if _has_ads_path_part(path):
        raise SecurityError("FILE_ACCESS_BLOCKED", "File reference failed security checks.")

    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise SecurityError("FILE_ACCESS_BLOCKED", "File reference failed security checks.") from exc

    if not resolved.is_relative_to(root):
        raise SecurityError("PATH_CONTAINMENT_FAILED", "File reference failed workspace containment checks.")

    _reject_reparse_path(root, path)

    try:
        file_stat = resolved.stat()
    except OSError as exc:
        raise SecurityError("FILE_ACCESS_BLOCKED", "File reference failed security checks.") from exc

    if require_file and not resolved.is_file():
        raise SecurityError("FILE_ACCESS_BLOCKED", "File reference failed security checks.")
    if getattr(file_stat, "st_nlink", 1) > 1:
        raise SecurityError("FILE_ACCESS_BLOCKED", "File reference failed security checks.")

    suffixes = frozenset(suffix.lower() for suffix in allowed_suffixes)
    if suffixes and resolved.suffix.lower() not in suffixes:
        raise SecurityError("UNSUPPORTED_FILE_TYPE", "Input file type is not allowed.")
    return resolved


def _reject_reparse_path(root: Path, candidate: Path) -> None:
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return

    current = root
    for part in relative.parts:
        current = current / part
        try:
            path_stat = current.lstat()
        except OSError as exc:
            raise SecurityError("FILE_ACCESS_BLOCKED", "File reference failed security checks.") from exc
        if current.is_symlink() or _is_windows_reparse_point(path_stat):
            raise SecurityError("FILE_ACCESS_BLOCKED", "File reference failed security checks.")


def _is_windows_reparse_point(path_stat: object) -> bool:
    file_attributes = getattr(path_stat, "st_file_attributes", 0)
    return bool(file_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _has_ads_path_part(path: Path) -> bool:
    anchor = path.anchor
    for part in path.parts:
        if part == anchor:
            continue
        if ":" in part:
            return True
    return False


def _looks_like_uri(value: str) -> bool:
    return re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value) is not None


def _is_unc_token(value: str) -> bool:
    return value.startswith("\\\\") or value.startswith("//")


def _has_drive_letter(value: str) -> bool:
    return re.match(r"^[A-Za-z]:", value) is not None


def _contains_control_char(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)
