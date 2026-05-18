# Fattern

[한국어](README.md)

Current version: **0.8.4**

Fattern estimates rough marker yield and quotation yield from DXF pattern files. The deterministic engine does the calculation; the Web UI and MCP are access layers.

```text
General users: Web UI
AI-assisted users: MCP + Web UI result review
```

Fattern is not a production-confirmed CAD nesting replacement. `quote_yield` is a quotation estimate. `minimum_yield` is the minimum length from the current deterministic marker layout.

## Install

Requires Python 3.11 or newer.

```powershell
python -m pip install https://github.com/woooya129-ai/fattern/archive/refs/heads/main.zip
```

After PyPI release, this can become:

```powershell
python -m pip install fattern
```

## Run

```powershell
fattern
```

This starts the local Web UI and creates `input/`, `output/`, and `config/` automatically.

## Folders

```text
fattern-workspace/
  input/
    Put DXF files here when using folder-based workflows

  output/
    Run outputs are saved here

  config/
    Default answers.json
```

Uploads from the Web UI are also saved under `output/`.

## Default Questionnaire

The Web UI shows these fields on the first screen. Unknown values can start with defaults.

```json
{
  "schema_version": "1.0",
  "fabric_width": 150,
  "unit": "cm",
  "size_ratio": {},
  "spacing": 0.2,
  "allowed_rotation": [0],
  "grainline_required": false,
  "nap_direction": "two_way",
  "shrinkage_percent": 0,
  "fabric_type": "unknown",
  "seam_allowance": {"status": "included"},
  "allowance_policy": {"mode": "fast_quote"}
}
```

If the pattern does not include seam allowance, set `seam_allowance.status` to `excluded`. Without a custom fallback width, Fattern applies the default `1/2 inch` rough allowance.

## Outputs

Each run is saved in its own folder.

```text
output/
  20260518-153012_Simple-T/
    marker_preview.svg
    marker_report.md
    marker_report.pdf
    report.csv
    result.json
    run_summary.txt
```

Files:

- `marker_preview.svg`: marker preview
- `marker_report.pdf`: shareable report
- `marker_report.md`: readable calculation report
- `report.csv`: spreadsheet and automation output
- `result.json`: full result for MCP, Codex, and Claude Code
- `run_summary.txt`: shortest summary

Example output:

![Simple-T marker layout output example](docs/assets/simple-t-marker-preview.svg)

## Web UI + MCP

The Web UI is for visual review. MCP is for AI clients to run the workflow.

```text
Codex or Claude Code
  -> call Fattern MCP
  -> calculate_marker_yield or estimate_workspace_dxf
  -> create output/run_id
  -> return Web UI URL
  -> user reviews marker preview
```

High-level MCP results include `run_id`, `output_dir`, `web_url`, `preview_url`, and `report_url`.

## Advisor

The Web UI includes a deterministic Advisor that works without an LLM.

- explains warning and blocker codes
- explains `cuttable_width`, `seam_allowance`, `nap_direction`, `grainline_required`, and `quote_yield`
- enables optional LLM Advisor only when a server-side API key is configured

API keys are not exposed to the browser. The LLM receives a sanitized result summary, not the original full DXF by default.

## CLI

Advanced users can still use the CLI.

```powershell
fattern estimate input\sample.dxf --fabric-width 150 --unit cm --seam-allowance-status included --nap-direction two_way --grainline-required no
```

## MCP

stdio server:

```powershell
fattern-mcp
```

or:

```powershell
fattern mcp-stdio
```

Use `estimate_workspace_dxf` first for DXF files already under the workspace. Use `register_input_file` for attached file content and remote-compatible flows.

More details:

- [Developer guide](docs/developer.md)
- [AI client guide](docs/ai-clients.md)

## Scope

Currently supported:

- closed `LWPOLYLINE`
- R12 legacy `POLYLINE + VERTEX + SEQEND`
- simple connected `LINE` loop fallback
- rough marker layout
- separated `minimum_yield` and `quote_yield`
- Web UI, CLI, MCP

Not a commercial marker CAD replacement:

- all DXF entity conversion
- stripe/plaid matching
- fold pieces, mirrored pairs
- production-confirmed nesting
- plotter-ready multi-page PDF

## Development

```powershell
python -m unittest discover -s tests
```

## License

Source-available, noncommercial use only.

- [LICENSE](LICENSE)
- [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)
- [NOTICE](NOTICE)
