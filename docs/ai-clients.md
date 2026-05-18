# AI Client Guide

Fattern supports two user routes.

```text
General user:
  fattern
  -> Web UI
  -> upload DXF
  -> review output/run_id

AI-assisted user:
  fattern
  -> connect Fattern MCP from Codex or Claude Code
  -> run estimate_workspace_dxf or calculate_marker_yield
  -> open returned web_url
```

## Codex

Use Fattern for DXF rough marker yield, quotation yield, and marker report generation.

Recommended instruction:

```text
When the user asks for 가요척, marker yield, DXF pattern estimate, or rough marker report:
- Use the Fattern MCP server.
- Prefer estimate_workspace_dxf for files under input/.
- Ask only for missing fabric_width, unit, seam_allowance status, nap_direction, and grainline_required.
- After completion, summarize minimum_yield, quote_yield, confidence, warnings, and web_url.
- Do not call quote_yield a production-confirmed marker yield.
```

MCP command:

```powershell
fattern-mcp
```

## Claude Code

Claude Code can expose MCP prompts as slash commands when the client supports it.

Use:

```text
/mcp__fattern__fattern
/mcp__fattern__fattern-estimate
```

Recommended workflow:

```text
1. Put DXF under input/.
2. Ask Claude Code to run Fattern.
3. Claude calls estimate_workspace_dxf with input/<file>.dxf.
4. Claude returns web_url and key yield numbers.
5. User opens the Web UI link to inspect marker_preview.svg.
```

## Tool Choice

Use `estimate_workspace_dxf` when the DXF is local to the project workspace.

```text
relative_path: input/Simple-T.dxf
fabric_width: 150
unit: cm
```

Use `register_input_file` when the MCP client provides file bytes directly or when remote MCP cannot read the local workspace.

## Result Contract

High-level results should include:

```text
run_id
output_dir
web_url
preview_url
report_url
minimum_yield
quote_yield
allowance_breakdown
confidence
warnings
errors
```

If a blocker appears, stop and explain the blocker before asking the user to rerun.
