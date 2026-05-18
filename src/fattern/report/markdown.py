"""Markdown report rendering for marker layout results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fattern.engine import EngineMessage, ExcludedCandidate, LayoutResult


@dataclass(frozen=True)
class ExcludedPiece:
    piece_id: str
    reason_code: str
    message: str
    layer: str | None = None


ExcludedReportItem = ExcludedPiece | ExcludedCandidate


def render_marker_report(
    result: LayoutResult,
    warnings: Sequence[EngineMessage] | None = None,
    excluded_pieces: Sequence[ExcludedReportItem] = (),
    csv_partial_fields: Sequence[str] | None = None,
    quote_decision: Mapping[str, Any] | None = None,
) -> str:
    """Render a Markdown report from LayoutResult and optional report lists."""

    warning_messages = tuple(warnings) if warnings is not None else tuple(
        message for message in result.messages if message.severity == "warning"
    )

    lines = [
        "# Marker Report",
        "",
        "## Layout",
        "",
        f"- fabric_width: {_fmt(result.fabric_width)} {escape_markdown(result.unit)}",
        f"- marker_length: {_fmt(result.marker_length)} {escape_markdown(result.unit)}",
        f"- efficiency: {_fmt(result.efficiency)}",
        f"- total_piece_area: {_fmt(result.total_piece_area)} {escape_markdown(result.unit)}^2",
        f"- clearance: {_fmt(result.clearance)} {escape_markdown(result.unit)}",
        f"- grainline_status: {escape_markdown(result.grainline_status)}",
        f"- one_way_fabric: {_optional_bool(result.one_way_fabric)}",
        f"- rotation_allowed_degrees: {escape_markdown(','.join(str(value) for value in result.rotation_allowed_degrees))}",
        f"- no_overlap: {_bool(result.no_overlap)}",
        f"- within_fabric_width: {_bool(result.within_fabric_width)}",
        "",
    ]

    if quote_decision is not None:
        lines.extend(_quote_lines(quote_decision, result.unit))

    lines.extend(["## Placements", ""])

    if result.placements:
        lines.append("| piece_id | layer | x | y | width | height | rotation_degrees |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
        for placement in result.placements:
            lines.append(
                "| "
                f"{escape_markdown(placement.piece_id)} | "
                f"{escape_markdown(placement.layer)} | "
                f"{_fmt(placement.x)} | "
                f"{_fmt(placement.y)} | "
                f"{_fmt(placement.width)} | "
                f"{_fmt(placement.height)} | "
                f"{placement.rotation_degrees} |"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Warnings", ""])
    if warning_messages:
        for message in warning_messages:
            lines.append(
                f"- `{escape_code(message.code)}` {escape_markdown(message.message)}"
            )
    else:
        lines.append("- none")

    partial_fields = tuple(csv_partial_fields) if csv_partial_fields is not None else (
        "piece_name",
        "size",
        "quantity",
        "grainline_status",
    )
    partial_text = ", ".join(partial_fields) if partial_fields else "none"
    lines.extend(
        [
            "",
            "## CSV Availability",
            "",
            f"- unavailable piece metadata fields stay empty in `report.csv`: {partial_text}",
        ]
    )

    lines.extend(["", "## Excluded Pieces", ""])
    if excluded_pieces:
        lines.append("| piece_id | layer | reason_code | message |")
        lines.append("| --- | --- | --- | --- |")
        for item in excluded_pieces:
            lines.append(
                "| "
                f"{escape_markdown(_excluded_piece_id(item))} | "
                f"{escape_markdown(_excluded_layer(item))} | "
                f"`{escape_code(item.reason_code)}` | "
                f"{escape_markdown(item.message)} |"
            )
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def escape_markdown(value: object) -> str:
    text = str(value)
    replacements = {
        "\\": "\\\\",
        "|": "\\|",
        "`": "\\`",
        "*": "\\*",
        "_": "\\_",
        "[": "\\[",
        "]": "\\]",
        "<": "&lt;",
        ">": "&gt;",
        "\n": "<br>",
        "\r": "",
    }
    return "".join(replacements.get(char, char) for char in text)


def escape_code(value: object) -> str:
    return str(value).replace("`", "").replace("\n", " ").replace("\r", " ")


def _quote_lines(quote_decision: Mapping[str, Any], unit: str) -> list[str]:
    minimum_yield = _mapping(quote_decision.get("minimum_yield"))
    quote_yield = _mapping(quote_decision.get("quote_yield"))
    confidence = _mapping(quote_decision.get("confidence"))
    breakdown = _mapping(quote_decision.get("allowance_breakdown"))
    reasons = _mapping(quote_decision.get("allowance_reasons"))
    output_unit = str(minimum_yield.get("unit") or unit)

    lines = [
        "## Quote Summary",
        "",
        f"- minimum_yield: {_fmt_number(minimum_yield.get('marker_length'))} {escape_markdown(output_unit)}",
        f"- quote_yield: {_fmt_number(quote_yield.get('final_yield'))} {escape_markdown(output_unit)}",
        f"- allowance_total: {_fmt_number(quote_yield.get('allowance_total'))} {escape_markdown(output_unit)}",
        f"- allowance_rate: {_fmt_number(quote_yield.get('allowance_rate_percent'))}%",
        f"- confidence_grade: {escape_markdown(confidence.get('grade', 'unknown'))}",
        f"- recommended_use: {escape_markdown(quote_yield.get('recommended_use', 'fast quote only'))}",
        "",
        "This is a quotation yield, not a production-confirmed marker yield.",
        "",
        "## Allowance Breakdown",
        "",
    ]
    if breakdown:
        lines.append("| item | value | reason |")
        lines.append("| --- | ---: | --- |")
        for item, value in breakdown.items():
            lines.append(
                "| "
                f"{escape_markdown(item)} | "
                f"{_fmt_number(value)} {escape_markdown(output_unit)} | "
                f"{escape_markdown(reasons.get(item, ''))} |"
            )
    else:
        lines.append("- none")
    lines.append("")
    return lines


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _fmt_number(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _fmt(float(value))
    return "0"


def _excluded_piece_id(item: ExcludedReportItem) -> str:
    if isinstance(item, ExcludedPiece):
        return item.piece_id
    return f"entity_{item.source_entity_index:04d}"


def _excluded_layer(item: ExcludedReportItem) -> str:
    layer = item.layer
    return layer if layer is not None else ""


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _optional_bool(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return _bool(value)


def _fmt(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"
