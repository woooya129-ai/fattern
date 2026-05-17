"""Transport-neutral MCP surface used by tests and stdio transport."""

from __future__ import annotations

from typing import Any

from .tools import McpToolRegistry

PROMPTS = (
    {
        "name": "fattern-help",
        "title": "Fattern Help",
        "description": "Show the Fattern workflow, required answers, and safe MCP call order.",
    },
    {
        "name": "fattern-estimate",
        "title": "Estimate Rough Marker",
        "description": "Guide a user through questionnaire answers and DXF-based rough marker estimation.",
    },
)


class FatternMcpServer:
    """Transport-neutral server facade for tools/list and tools/call."""

    def __init__(self, registry: McpToolRegistry | None = None) -> None:
        self.registry = registry or McpToolRegistry()

    def tools_list(self) -> dict[str, Any]:
        return {"tools": self.registry.list_tools()}

    def tools_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.registry.call_tool(name, arguments)

    def prompts_list(self) -> dict[str, Any]:
        return {"prompts": [dict(prompt) for prompt in PROMPTS]}

    def prompts_get(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if name == "fattern-help":
            text = (
                "Fattern workflow: ask get_estimation_questionnaire, collect answers, register DXF content, "
                "then call create_job -> register_input_file -> parse_dxf -> extract_pattern_pieces -> "
                "calculate_piece_metrics -> estimate_marker_layout -> render_marker_svg -> export_artifacts. "
                "Do not pass filesystem paths to MCP tools. Stop immediately when any tool returns a blocker error."
            )
            return _prompt_response("Fattern Help", text)
        if name == "fattern-estimate":
            text = (
                "Ask for: DXF file, fabric_width, unit, dxf_unit_hint, seam_allowance_included, "
                "seam_allowance_width, grainline_status, one_way_fabric, rotation_allowed_degrees, clearance. "
                "Default rotation is 0 only. Do not rotate grainline-sensitive patterns unless the user explicitly allows it."
            )
            return _prompt_response("Estimate Rough Marker", text)
        raise KeyError(name)


def _prompt_response(description: str, text: str) -> dict[str, Any]:
    return {
        "description": description,
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": text},
            }
        ],
    }
