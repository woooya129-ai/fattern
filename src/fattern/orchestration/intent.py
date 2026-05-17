"""Schema-bound UserIntent and ClarificationRequest orchestration helpers.

This module only normalizes user-facing intent data and asks for missing
information. It does not execute the MCP tool chain or calculate geometry,
marker length, efficiency, or SVG paths.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from importlib import resources
from pathlib import Path
from typing import Any

from fattern.engine.metrics import default_seam_allowance_width
from fattern.mcp.validation import ToolValidationError, validate_input
from fattern.schemas import DEFAULT_CLEARANCE_CM, DEFAULT_ROTATION_ALLOWED_DEGREES, ID_PATTERN, SUPPORTED_UNITS

from .fabric_presets import QUESTIONNAIRE_FIELDS, fabric_width_allowed_answers

SCHEMA_VERSION = "1.0"
VALID_INTENTS = {"estimate_yield", "parse_only", "render_preview", "explain_result", "ask_clarification"}
VALID_UNITS = set(SUPPORTED_UNITS)
VALID_DXF_UNIT_HINTS = {"auto", *VALID_UNITS}
VALID_ROTATIONS = {0, 90, 180, 270}
VALID_GRAINLINE_STATUS = {"present", "missing", "unknown"}


class UserIntentValidationError(ValueError):
    pass


class ClarificationValidationError(ValueError):
    pass


def normalize_user_intent(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize untrusted user input into the UserIntent schema contract."""

    source = raw or {}
    unit = _normalize_unit(source.get("unit"))
    fabric = _normalize_fabric(source, unit)
    rules = _normalize_rules(source, unit)
    missing_fields = _missing_fields(source, unit, fabric, rules)

    intent = {
        "schema_version": SCHEMA_VERSION,
        "intent": _normalize_intent(source.get("intent"), missing_fields),
        "unit": unit,
        "dxf_unit_hint": _normalize_dxf_unit_hint(source.get("dxf_unit_hint")),
        "fabric": fabric,
        "rules": rules,
        "piece_overrides": _normalize_piece_overrides(source.get("piece_overrides")),
        "missing_fields": missing_fields,
        "confidence": 0.9 if not missing_fields else 0.4,
    }
    validate_user_intent(intent)
    return intent


def build_clarification_request(user_intent: dict[str, Any]) -> dict[str, Any] | None:
    """Build a ClarificationRequest for schema-level missing fields."""

    validate_user_intent(user_intent)
    missing_fields = user_intent.get("missing_fields", [])
    if not missing_fields:
        return None

    questions = [_question_for_field(field) for field in missing_fields]
    request = {
        "schema_version": SCHEMA_VERSION,
        "blocking": True,
        "questions": questions,
    }
    validate_clarification_request(request)
    return request


def build_estimation_questionnaire() -> dict[str, Any]:
    request = {
        "schema_version": SCHEMA_VERSION,
        "blocking": True,
        "questions": [_question_for_field(field) for field in QUESTIONNAIRE_FIELDS],
    }
    validate_clarification_request(request)
    return request


def validate_user_intent(user_intent: dict[str, Any]) -> None:
    try:
        validate_input(_load_schema("user-intent.schema.json"), user_intent)
    except ToolValidationError as exc:
        raise UserIntentValidationError("UserIntent schema validation failed") from exc


def validate_clarification_request(request: dict[str, Any]) -> None:
    try:
        validate_input(_load_schema("clarification.schema.json"), request)
    except ToolValidationError as exc:
        raise ClarificationValidationError("ClarificationRequest schema validation failed") from exc


def _normalize_intent(value: Any, missing_fields: list[str]) -> str:
    if isinstance(value, str) and value in VALID_INTENTS:
        return value
    if missing_fields:
        return "ask_clarification"
    return "estimate_yield"


def _normalize_unit(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_UNITS:
            return normalized
    return None


def _normalize_dxf_unit_hint(value: Any) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_DXF_UNIT_HINTS:
            return normalized
    return "auto"


def _normalize_fabric(source: dict[str, Any], unit: str | None) -> dict[str, Any]:
    fabric_source = source.get("fabric") if isinstance(source.get("fabric"), dict) else {}
    width = fabric_source.get("width", source.get("fabric_width"))
    width_unit = fabric_source.get("width_unit", source.get("fabric_width_unit", unit))
    normalized_width = width if isinstance(width, (int, float)) and not isinstance(width, bool) and width >= 1 else None
    return {
        "width": normalized_width,
        "width_unit": _normalize_unit(width_unit),
    }


def _normalize_rules(source: dict[str, Any], unit: str | None) -> dict[str, Any]:
    rules_source = source.get("rules") if isinstance(source.get("rules"), dict) else {}
    seam_allowance_included = _normalize_optional_bool(rules_source.get("seam_allowance_included"))
    return {
        "grainline_required": _normalize_bool(rules_source.get("grainline_required"), default=True),
        "grainline_status": _normalize_grainline_status(
            rules_source.get("grainline_status", source.get("grainline_status"))
        ),
        "rotation_allowed_degrees": _normalize_rotations(rules_source.get("rotation_allowed_degrees")),
        "seam_allowance_included": seam_allowance_included,
        "seam_allowance_width": _normalize_seam_allowance_width(
            rules_source.get("seam_allowance_width", source.get("seam_allowance_width")),
            unit,
            seam_allowance_included,
        ),
        "one_way_fabric": _normalize_optional_bool(rules_source.get("one_way_fabric", source.get("one_way_fabric"))),
        "clearance": _normalize_clearance(rules_source.get("clearance", source.get("clearance"))),
    }


def _normalize_piece_overrides(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    overrides = []
    for item in value:
        if not isinstance(item, dict):
            continue
        piece_name = item.get("piece_name")
        quantity = item.get("quantity")
        rotations = _normalize_rotations(item.get("rotation_allowed_degrees"))
        if isinstance(piece_name, str) and 1 <= len(piece_name) <= 120 and isinstance(quantity, int) and quantity >= 1:
            overrides.append(
                {
                    "piece_name": piece_name,
                    "quantity": quantity,
                    "rotation_allowed_degrees": rotations,
                }
            )
    return overrides


def _missing_fields(
    source: dict[str, Any],
    unit: str | None,
    fabric: dict[str, Any],
    rules: dict[str, Any],
) -> list[str]:
    missing = []
    if not _has_file_reference(source):
        missing.append("dxf_file")
    if fabric["width"] is None:
        missing.append("fabric_width")
    if unit is None:
        missing.append("unit")
    if rules["seam_allowance_included"] is None:
        missing.append("seam_allowance_included")
    if rules["one_way_fabric"] is None:
        missing.append("one_way_fabric")
    return missing


def _has_file_reference(source: dict[str, Any]) -> bool:
    file_id = source.get("file_id")
    dxf_file = source.get("dxf_file")
    has_file_id = isinstance(file_id, str) and file_id.startswith("file_") and re.fullmatch(ID_PATTERN, file_id) is not None
    has_uploaded_file = isinstance(dxf_file, str) and dxf_file.strip() != ""
    return has_file_id or has_uploaded_file


def _question_for_field(field: str) -> dict[str, Any]:
    questions = {
        "dxf_file": {
            "question": "DXF 파일을 업로드하거나 file_id를 제공해줘.",
            "allowed_answers": ["file_id"],
        },
        "fabric_width": {
            "question": "사용할 원단 폭을 선택하거나 직접 숫자로 알려줘.",
            "allowed_answers": fabric_width_allowed_answers(),
        },
        "unit": {
            "question": "결과와 원단 폭에 사용할 단위를 선택해줘.",
            "allowed_answers": list(SUPPORTED_UNITS),
        },
        "dxf_unit_hint": {
            "question": "DXF 좌표 단위는 자동 추정할까, 직접 지정할까?",
            "allowed_answers": ["auto", *SUPPORTED_UNITS],
        },
        "grainline_status": {
            "question": "DXF에서 식서선이 확인돼?",
            "allowed_answers": ["present", "missing", "unknown"],
        },
        "piece_quantity": {
            "question": "피스별 수량을 알려줘.",
            "allowed_answers": ["quantity_by_piece"],
        },
        "size_ratio": {
            "question": "사이즈별 수량 비율을 알려줘.",
            "allowed_answers": ["{}", "{\"M\": 1}", "{\"S\": 1, \"M\": 2, \"L\": 1}"],
        },
        "spacing": {
            "question": "피스 사이 최소 간격을 선택 단위 기준 숫자로 알려줘.",
            "allowed_answers": ["0", "0.2", "5"],
        },
        "allowed_rotation": {
            "question": "허용 회전 각도를 배열로 알려줘.",
            "allowed_answers": ["[0]", "[0, 180]", "[0, 90, 180, 270]"],
        },
        "grainline_required": {
            "question": "식서선이 필수 조건인지 알려줘.",
            "allowed_answers": ["true", "false"],
        },
        "nap_direction": {
            "question": "원단 방향성을 알려줘.",
            "allowed_answers": ["one_way", "two_way", "none", "no_nap", "not_one_way"],
        },
        "shrinkage_percent": {
            "question": "수축률을 길이 방향 퍼센트 숫자로 알려줘.",
            "allowed_answers": ["0", "3", "5"],
        },
        "fabric_type": {
            "question": "원단 종류를 알려줘.",
            "allowed_answers": ["woven", "knit", "unknown"],
        },
        "stretch_direction": {
            "question": "니트라면 스트레치 방향을 알려줘.",
            "allowed_answers": ["lengthwise", "crosswise", "bias", "unknown"],
        },
        "seam_allowance": {
            "question": "시접 포함 여부와 fallback 폭을 객체로 알려줘.",
            "allowed_answers": ["{\"status\": \"included\"}", "{\"status\": \"excluded\", \"fallback_width\": 1}"],
        },
        "grainline_rule": {
            "question": "식서 방향 규칙을 알려줘.",
            "allowed_answers": ["required", "optional", "unknown"],
        },
        "rotation_rule": {
            "question": "허용 회전 각도를 알려줘.",
            "allowed_answers": ["0", "0,180", "0,90,180,270"],
        },
        "rotation_allowed_degrees": {
            "question": "허용 회전 각도를 선택해줘.",
            "allowed_answers": ["0", "0,180", "0,90,180,270"],
        },
        "seam_allowance_included": {
            "question": "시접이 패턴에 포함되어 있어?",
            "allowed_answers": ["yes", "no", "unknown"],
        },
        "seam_allowance_width": {
            "question": "시접이 없다면 평균 시접값을 쓸까?",
            "allowed_answers": ["auto: mm 10 / cm 1.0 / m 0.01 / inch 0.375 / ft 0.03125 / yd 0.0104167", "number", "skip"],
        },
        "one_way_fabric": {
            "question": "원웨이 원단이야?",
            "allowed_answers": ["yes", "no", "unknown"],
        },
        "clearance": {
            "question": "피스 사이 최소 간격을 지정할까?",
            "allowed_answers": ["default 0.2", "number"],
        },
    }
    payload = deepcopy(questions[field])
    payload["field"] = field
    return payload


def _normalize_bool(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _normalize_optional_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y"}:
            return True
        if normalized in {"false", "no", "n"}:
            return False
    return None


def _normalize_rotations(value: Any) -> list[int]:
    if not isinstance(value, list):
        return list(DEFAULT_ROTATION_ALLOWED_DEGREES)
    rotations = []
    for item in value:
        if isinstance(item, int) and not isinstance(item, bool) and item in VALID_ROTATIONS and item not in rotations:
            rotations.append(item)
    return rotations or list(DEFAULT_ROTATION_ALLOWED_DEGREES)


def _normalize_grainline_status(value: Any) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_GRAINLINE_STATUS:
            return normalized
    return "unknown"


def _normalize_clearance(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return value
    return DEFAULT_CLEARANCE_CM


def _normalize_seam_allowance_width(value: Any, unit: str | None, seam_allowance_included: bool | None) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    if seam_allowance_included is not False or unit is None:
        return None
    return default_seam_allowance_width(unit)


def _load_schema(name: str) -> dict[str, Any]:
    schema_path = Path(__file__).resolve().parents[3] / "schemas" / name
    if schema_path.is_file():
        with schema_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    schema_text = resources.files("fattern.schemas").joinpath(name).read_text(encoding="utf-8")
    return json.loads(schema_text)
