"""Markdown report rendering for marker layout results."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

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
        f"- no_overlap: {_bool(result.no_overlap)}",
        f"- within_fabric_width: {_bool(result.within_fabric_width)}",
        "",
        "## Placements",
        "",
    ]

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


def _excluded_piece_id(item: ExcludedReportItem) -> str:
    if isinstance(item, ExcludedPiece):
        return item.piece_id
    return f"entity_{item.source_entity_index:04d}"


def _excluded_layer(item: ExcludedReportItem) -> str:
    layer = item.layer
    return layer if layer is not None else ""


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _fmt(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text if text else "0"
