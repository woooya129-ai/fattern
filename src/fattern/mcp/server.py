"""Transport-neutral MCP surface used by tests and stdio transport."""

from __future__ import annotations

from typing import Any

from .tools import McpToolRegistry

PROMPTS = (
    {
        "name": "fattern",
        "title": "Fattern Guide",
        "description": "Start the Fattern MCP guide from a slash prompt.",
    },
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

FATTERN_GUIDE_PROMPT = """Fattern MCP guide.

Use this when the user types /fattern or asks how to run Fattern through MCP.

Rules:
- Prefer estimate_workspace_dxf when the DXF is already under the current workspace, for example input/Simple-T.dxf.
- Only pass workspace-relative DXF paths. Never pass absolute paths, .., file:// URLs, or non-DXF files.
- If the client provides attached DXF bytes instead of a workspace file, register it with register_input_file.
- Use get_estimation_questionnaire as a reference guide, not as a forced popup.
- Required user decisions: fabric_width or cuttable_width, unit, seam_allowance status, nap_direction, grainline_required.
- Optional quote decision: allowance_policy.mode can be fast_quote, sample_estimate, or bulk_precheck.
- If seam_allowance.status is excluded and fallback_width is missing, Fattern applies the default 1/2 inch allowance: 12.7 mm, 1.27 cm, 0.5 inch.
- calculate_marker_yield returns minimum_yield separately from quote_yield; do not call quote_yield a production-confirmed marker yield.
- High-level MCP results include run_id, output_dir, web_url, preview_url, and report_url when run persistence is enabled.
- Stop when any tool returns a blocker error and explain the blocker before continuing.

Safe order:
1. get_estimation_questionnaire
2. estimate_workspace_dxf for workspace files, or create_job -> register_input_file for attached content
3. calculate_marker_yield if you registered content manually
4. Explain minimum_yield, quote_yield, allowance_breakdown, confidence, and web_url from tool output
"""

FATTERN_ESTIMATE_PROMPT = """Guide the user through a Fattern rough marker estimate.

Collect only missing values:
- DXF path under the workspace, or DXF content to register with register_input_file
- fabric_width or cuttable_width
- unit
- seam_allowance.status: included or excluded
- nap_direction: one_way, two_way, none, no_nap, or not_one_way
- grainline_required
- allowance_policy.mode when the user wants a quote profile

Defaults when the user does not specify them:
- allowed_rotation: [0]
- size_ratio: {}
- piece_quantity: {}
- spacing: 0.2
- shrinkage_percent: 0
- fabric_type: unknown
- seam allowance fallback: 1/2 inch when seam_allowance.status is excluded and fallback_width is absent
- allowance_policy.mode: fast_quote

Default rotation is 0 only. Do not rotate grainline-sensitive patterns unless the user explicitly allows it.
After a successful high-level call, give the user the web_url so they can inspect the marker preview in the Web UI.
"""


class FatternMcpServer:
    """Transport-neutral server facade for tools/list and tools/call."""

    def __init__(self, registry: McpToolRegistry | None = None) -> None:
        self.registry = registry or McpToolRegistry(persist_runs=True)

    def tools_list(self) -> dict[str, Any]:
        return {"tools": self.registry.list_tools()}

    def tools_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.registry.call_tool(name, arguments)

    def prompts_list(self) -> dict[str, Any]:
        return {"prompts": [dict(prompt) for prompt in PROMPTS]}

    def prompts_get(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if name in {"fattern", "fattern-help"}:
            return _prompt_response("Fattern Guide", FATTERN_GUIDE_PROMPT)
        if name == "fattern-estimate":
            return _prompt_response("Estimate Rough Marker", FATTERN_ESTIMATE_PROMPT)
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
