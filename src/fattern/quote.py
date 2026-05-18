"""Quote-yield decision layer built on deterministic marker output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import ceil
from typing import Any


UNIT_PER_METER = {
    "mm": 1000.0,
    "cm": 100.0,
    "m": 1.0,
    "inch": 39.37007874015748,
    "ft": 3.280839895013123,
    "yd": 1.0936132983377078,
}

ALLOWANCE_POLICY_PRESETS = {
    "fast_quote": {
        "rounding_unit_m": 0.05,
        "base_buffer_percent": 5.0,
        "cutting_loss_percent": 2.0,
        "end_loss_length_m": 0.03,
        "fabric_defect_buffer_percent": 1.0,
        "unknown_risk_buffer_percent": 3.0,
        "apply_warning_penalty": True,
    },
    "sample_estimate": {
        "rounding_unit_m": 0.01,
        "base_buffer_percent": 2.0,
        "cutting_loss_percent": 1.0,
        "end_loss_length_m": 0.01,
        "fabric_defect_buffer_percent": 0.0,
        "unknown_risk_buffer_percent": 1.0,
        "apply_warning_penalty": True,
    },
    "bulk_precheck": {
        "rounding_unit_m": 0.01,
        "base_buffer_percent": 2.0,
        "cutting_loss_percent": 1.5,
        "end_loss_length_m": 0.02,
        "fabric_defect_buffer_percent": 0.5,
        "unknown_risk_buffer_percent": 1.5,
        "apply_warning_penalty": True,
    },
}

WARNING_PENALTY_PERCENT = {
    "GRAINLINE_NOT_DETECTED": 2.0,
    "SEAM_ALLOWANCE_DEFAULT_APPLIED": 1.0,
    "DXF_UNIT_AUTOSCALE_APPLIED": 1.0,
    "UNVERIFIED_DXF_VERSION": 1.0,
    "BBOX_FALLBACK_USED": 2.0,
    "LINE_LOOP_CONTOUR_CONNECTED": 1.0,
    "EXTRACTION_MODE_FALLBACK": 1.0,
    "SHRINKAGE_PERCENT_NOT_APPLIED": 1.5,
}

WARNING_REASON = {
    "GRAINLINE_NOT_DETECTED": "grainline not verified",
    "SEAM_ALLOWANCE_DEFAULT_APPLIED": "default seam allowance applied",
    "DXF_UNIT_AUTOSCALE_APPLIED": "DXF unit auto-scaled",
    "UNVERIFIED_DXF_VERSION": "DXF version is unverified",
    "BBOX_FALLBACK_USED": "bbox fallback layout was used",
    "LINE_LOOP_CONTOUR_CONNECTED": "outline was stitched from line segments",
    "EXTRACTION_MODE_FALLBACK": "fallback extraction mode was used",
    "SHRINKAGE_PERCENT_NOT_APPLIED": "shrinkage input was not applied",
}


def build_quote_decision(
    *,
    marker_length: float,
    unit: str,
    allowance_policy: Mapping[str, Any] | None,
    warnings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return minimum yield, quote yield, allowance breakdown, and confidence."""

    policy = _resolved_policy(allowance_policy, unit)
    warning_codes = tuple(_warning_codes(warnings))
    warning_penalty_percent = _warning_penalty_percent(warning_codes) if policy["apply_warning_penalty"] else 0.0

    base_yield = max(0.0, float(marker_length))
    allowance_breakdown = {
        "base_buffer": _percent_value(base_yield, policy["base_buffer_percent"]),
        "cutting_loss": _percent_value(base_yield, policy["cutting_loss_percent"]),
        "end_loss": policy["end_loss_length"],
        "fabric_defect_buffer": _percent_value(base_yield, policy["fabric_defect_buffer_percent"]),
        "unknown_risk_buffer": _percent_value(base_yield, policy["unknown_risk_buffer_percent"]),
        "warning_penalty": _percent_value(base_yield, warning_penalty_percent),
    }
    subtotal = base_yield + sum(allowance_breakdown.values())
    final_yield = _round_up(subtotal, policy["rounding_unit"])
    allowance_breakdown["rounding"] = max(0.0, final_yield - subtotal)
    allowance_total = final_yield - base_yield
    allowance_rate = (allowance_total / base_yield * 100.0) if base_yield > 0 else 0.0

    confidence = _confidence(warning_codes)
    return {
        "minimum_yield": {
            "marker_length": base_yield,
            "unit": unit,
            "source": "deterministic_marker_layout",
        },
        "quote_yield": {
            "base_yield": base_yield,
            "unit": unit,
            "allowance_total": allowance_total,
            "allowance_rate_percent": allowance_rate,
            "final_yield": final_yield,
            "rounding_rule": f"round_up_{_fmt(policy['rounding_unit'])}{unit}",
            "policy_mode": policy["mode"],
            "recommended_use": _recommended_use(confidence["grade"]),
        },
        "allowance_breakdown": allowance_breakdown,
        "allowance_reasons": {
            "base_buffer": f"{policy['mode']} base buffer {policy['base_buffer_percent']:g}%",
            "cutting_loss": f"default cutting loss {policy['cutting_loss_percent']:g}%",
            "end_loss": "end loss length for quote safety",
            "fabric_defect_buffer": f"fabric defect buffer {policy['fabric_defect_buffer_percent']:g}%",
            "unknown_risk_buffer": f"unknown risk buffer {policy['unknown_risk_buffer_percent']:g}%",
            "warning_penalty": _warning_reason_text(warning_codes, warning_penalty_percent),
            "rounding": f"rounded up to {_fmt(policy['rounding_unit'])} {unit}",
        },
        "allowance_policy": policy,
        "confidence": confidence,
    }


def _resolved_policy(allowance_policy: Mapping[str, Any] | None, unit: str) -> dict[str, Any]:
    source = allowance_policy or {}
    mode = source.get("mode", "fast_quote")
    if mode not in ALLOWANCE_POLICY_PRESETS:
        mode = "fast_quote"
    preset = ALLOWANCE_POLICY_PRESETS[mode]
    return {
        "mode": mode,
        "rounding_unit": _policy_number(source, "rounding_unit", _unit_length(preset["rounding_unit_m"], unit)),
        "base_buffer_percent": _policy_number(source, "base_buffer_percent", preset["base_buffer_percent"]),
        "cutting_loss_percent": _policy_number(source, "cutting_loss_percent", preset["cutting_loss_percent"]),
        "end_loss_length": _policy_number(source, "end_loss_length", _unit_length(preset["end_loss_length_m"], unit)),
        "fabric_defect_buffer_percent": _policy_number(
            source,
            "fabric_defect_buffer_percent",
            preset["fabric_defect_buffer_percent"],
        ),
        "unknown_risk_buffer_percent": _policy_number(
            source,
            "unknown_risk_buffer_percent",
            preset["unknown_risk_buffer_percent"],
        ),
        "apply_warning_penalty": _policy_bool(
            source,
            "apply_warning_penalty",
            bool(preset["apply_warning_penalty"]),
        ),
    }


def _policy_number(source: Mapping[str, Any], key: str, default: float) -> float:
    value = source.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, float(value))
    return float(default)


def _policy_bool(source: Mapping[str, Any], key: str, default: bool) -> bool:
    value = source.get(key)
    return value if isinstance(value, bool) else default


def _unit_length(meters: float, unit: str) -> float:
    return meters * UNIT_PER_METER.get(unit, UNIT_PER_METER["cm"])


def _warning_codes(warnings: Sequence[Mapping[str, Any]]) -> list[str]:
    codes: list[str] = []
    for warning in warnings:
        code = warning.get("code")
        if isinstance(code, str) and code not in codes:
            codes.append(code)
    return codes


def _warning_penalty_percent(warning_codes: Sequence[str]) -> float:
    return sum(WARNING_PENALTY_PERCENT.get(code, 0.0) for code in warning_codes)


def _confidence(warning_codes: Sequence[str]) -> dict[str, Any]:
    risk_score = _warning_penalty_percent(warning_codes)
    if risk_score <= 0:
        grade = "A"
    elif risk_score <= 2:
        grade = "B"
    elif risk_score <= 5:
        grade = "C"
    else:
        grade = "D"
    reasons = [WARNING_REASON[code] for code in warning_codes if code in WARNING_REASON]
    if not reasons:
        reasons = ["deterministic marker layout completed without quote-risk warnings"]
    return {
        "grade": grade,
        "reason": reasons,
    }


def _recommended_use(grade: str) -> str:
    if grade == "A":
        return "rough quote"
    if grade == "B":
        return "fast quote"
    if grade == "C":
        return "fast quote only"
    return "manual review before quote"


def _warning_reason_text(warning_codes: Sequence[str], warning_penalty_percent: float) -> str:
    if warning_penalty_percent <= 0:
        return "warning penalty disabled or no quote-risk warnings"
    reasons = [WARNING_REASON[code] for code in warning_codes if code in WARNING_REASON]
    return f"{warning_penalty_percent:g}% warning penalty: {', '.join(reasons)}"


def _percent_value(base: float, percent: float) -> float:
    return base * percent / 100.0


def _round_up(value: float, unit: float) -> float:
    if unit <= 0:
        return value
    return ceil(value / unit) * unit


def _fmt(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"
