# Fattern

[한국어](README.md)

A CLI/MCP tool for fast rough marker-yield estimation from DXF garment pattern files.

Fattern means **FAST + PATTERN = FATTERN**.

Current version: **0.8.0**

This repository is **source-available, noncommercial use only** under **PolyForm Noncommercial License 1.0.0 + a separate Commercial License**.

## Quick Understanding

- Fattern is not an LLM calculator. It is a **DXF-based deterministic marker yield engine + quote-yield decision layer**.
- Inputs are a DXF pattern, fabric conditions, and optional quote allowance policy. Outputs separate minimum yield from quotation yield.
- Main artifacts are `result.json`, `marker_preview.svg`, `marker_report.md`, `marker_report.pdf`, and `report.csv`.
- v0.8.0 returns `minimum_yield`, `quote_yield`, `allowance_breakdown`, and `confidence` through the high-level MCP tool `calculate_marker_yield` and reports.
- It is not a production final-yield system or a replacement for commercial CAD nesting.

## Installation

Python **3.11 or newer** is required.

```powershell
git clone <repo-url>
cd fattern
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Verify the install:

```powershell
fattern --help
fattern questionnaire
```

To run directly from the source tree without installing:

```powershell
$env:PYTHONPATH = "src"
python -m fattern --help
```

## How To Use

The easiest workflow is the `input/` folder workflow.

1. Create `input/`.
2. Put one DXF file in it.
3. Create `input/answers.json`.
4. Run `python -m fattern estimate`.
5. Open the newly created folder under `output/`.

Read the outputs in this order:

1. `marker_report.md`: human-readable summary with minimum yield, quote yield, allowance breakdown, and warnings.
2. `marker_preview.svg`: visual marker preview. Check width overflow and rotations.
3. `report.csv`: per-piece coordinates and rotations for spreadsheets or downstream automation.
4. `result.json`: tool-chain result for MCP, Codex, Claude Code, or scripts.
5. `marker_report.pdf`: one-page report for sharing.

When DXF layers are unclear, inspect `layer_audit` from `parse_dxf` or `extract_pattern_pieces`. It shows entity counts by layer, grainline candidate source, confidence, and mapping status. Numeric layer `7` remains an AAMA/ASTM candidate only; Fattern does not treat it as a verified CAD vendor mapping.

Layout still uses the existing BLF + beam-search structure. In v0.8.0, the marker engine produces the minimum requirement and the quote layer separately adds practical allowance and confidence. This is still not commercial CAD-grade final nesting.

## One-Line Use

Put one DXF file and `answers.json` in `input/`, then run:

```powershell
python -m fattern estimate
```

You can also pass options directly:

```powershell
python -m fattern estimate input\sample.dxf --fabric-width 150 --unit cm --seam-allowance-status included --nap-direction two_way --grainline-required no --spacing 0.2 --allowed-rotation 0
```

Results are written to `output/YYYYMMDD-HHMMSS_DXFNAME/`.

```text
output/
  20260517-223500_Simple-T/
    marker_preview.svg
    marker_report.md
    marker_report.pdf
    report.csv
    result.json
```

Output example:

![Simple-T marker layout output example](docs/assets/simple-t-marker-preview.svg)

## Easiest Flow

1. Create `input/`.
2. Put one DXF file in it.
3. Print the questionnaire.

```powershell
python -m fattern questionnaire
```

4. Create `input/answers.json`.

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

5. Run:

```powershell
python -m fattern estimate
```

The `input/` workflow is easiest for non-technical users. Direct DXF paths are better for scripts. MCP tools do not accept filesystem paths; clients must register file content with `register_input_file`.

## Codex And Claude Code

Codex one-liner:

```text
input 폴더의 DXF와 answers.json으로 python -m fattern estimate 실행하고 output 결과를 요약해줘.
```

Claude Code one-liner:

```text
Run python -m fattern estimate using the DXF and answers.json in input/, then summarize the files created under output/.
```

## Questionnaire

`python -m fattern questionnaire` asks for:

- `dxf_file`: DXF file or MCP file_id
- `fabric_width`: fabric width
- `unit`: output unit, `mm`, `cm`, `m`, `inch`, `ft`, `yd`
- `size_ratio`: quantity ratio by size
- `piece_quantity`: additional quantity by piece
- `spacing`: minimum spacing between pieces
- `allowed_rotation`: allowed rotations
- `grainline_required`: whether grainline is mandatory
- `nap_direction`: `one_way`, `two_way`, `none`, `no_nap`, or `not_one_way`
- `shrinkage_percent`: length-direction shrinkage percent
- `fabric_type`: `woven`, `knit`, or `unknown`
- `stretch_direction`: knit stretch direction
- `seam_allowance`: seam allowance status object
- `allowance_policy`: quote allowance policy, `fast_quote`, `sample_estimate`, or `bulk_precheck`

## Minimum Yield And Quote Yield

Starting in v0.8.0, `calculate_marker_yield` separates the engine result from the quotation result.

```text
minimum_yield = minimum requirement from deterministic marker layout
quote_yield = minimum_yield plus practical allowance from allowance_policy
```

The default `allowance_policy.mode` is `fast_quote`. If `rounding_unit` and `end_loss_length` are absent, Fattern converts `0.05 m` rounding and `0.03 m` end loss into the selected unit.

```json
{
  "allowance_policy": {
    "mode": "fast_quote",
    "rounding_unit": 5,
    "base_buffer_percent": 5,
    "cutting_loss_percent": 2,
    "end_loss_length": 3,
    "fabric_defect_buffer_percent": 1,
    "unknown_risk_buffer_percent": 3,
    "apply_warning_penalty": true
  }
}
```

This example assumes `unit: "cm"`. When `apply_warning_penalty` is enabled, warnings such as `GRAINLINE_NOT_DETECTED`, `SEAM_ALLOWANCE_DEFAULT_APPLIED`, `DXF_UNIT_AUTOSCALE_APPLIED`, and `BBOX_FALLBACK_USED` affect quote buffer and confidence.

## Fabric Width Presets

There is no single worldwide standard, so Fattern presents common working widths and lets users enter the actual width.

- `44-45 in / 112-115 cm`: basic apparel, quilting cotton, crafts
- `54 in / 137 cm`: apparel, home decor, some upholstery fabrics
- `58-60 in / 147-152 cm`: wide apparel fabrics, knits, dresses, coats
- `108 in / 274 cm`: bedding, quilt backing, large panels
- `118 in / 300 cm`: extra-wide curtains and sheer drapery
- `custom`: enter the actual fabric width

## Grainline And Rotation

Grainline is critical for garment marker planning. Fattern defaults to `0` degrees only.

If rotation is acceptable, the user must explicitly pass `--rotation 0,180` or `--rotation 0,90,180,270`. When grainline is missing or unknown and rotation is allowed, the result includes a warning.

For one-way fabric, Fattern blocks calculation when piece-level grainline cannot be detected from the DXF. Fix the DXF grainline layer before continuing.

See [docs/marker-rules.md](docs/marker-rules.md) for detailed marker rules.

## Seam Allowance Defaults

When seam allowance is not included, set `seam_allowance` to `{"status": "excluded"}`. If `fallback_width` is absent, Fattern applies a rough average allowance based on `1/2 inch` in the selected unit.

- `mm`: `12.7`
- `cm`: `1.27`
- `m`: `0.0127`
- `inch`: `0.5`
- `ft`: `0.0416667`
- `yd`: `0.0138889`

This is a rough expansion, not an exact CAD offset-curve operation.

## DXF Unit Autoscale

The high-level `estimate` path currently uses `auto` DXF coordinate handling only. `--dxf-unit` accepts `auto` for this path.

```powershell
python -m fattern estimate input\sample.dxf --fabric-width 150 --unit cm --dxf-unit auto --seam-allowance-status included --nap-direction two_way --grainline-required no
```

## SVG Output

`marker_preview.svg` shows the fabric boundary, placed pattern outlines, fabric width, marker length, grainline status, allowed rotations, and a grainline direction indicator in the side information panel.

## MCP

Run the stdio server:

```powershell
python -m fattern mcp-stdio
```

Example config:

```json
{
  "command": "python",
  "args": ["-m", "fattern", "mcp-stdio"],
  "cwd": "C:\\obs\\fattern"
}
```

If an MCP client exposes prompts in a slash UI, press `/` and choose `fattern`, or run `/fattern`, to show the start guide. The server supports `prompts/list` and `prompts/get`, and provides `fattern`, `fattern-help`, and `fattern-estimate` prompts. Slash visibility depends on client support.

`/fattern` does not force a questionnaire popup. It is an MCP prompt that tells the host AI how to register DXF content, collect required answers, apply defaults, and call tools in order.

Do not pass DXF filesystem paths to MCP tools. The safe order is:

```text
get_estimation_questionnaire
create_job
register_input_file
parse_dxf
extract_pattern_pieces
calculate_piece_metrics
estimate_marker_layout
render_marker_svg
export_artifacts
```

Stop the chain if a tool returns a `severity=blocker` error.

## Supported Scope

- Closed LWPOLYLINE
- R12 `POLYLINE + VERTEX + SEQEND`
- Closed outlines stitched from connected `LINE` segments
- Bbox baseline + polygon-aware compact rough marker layout
- Shelf compaction, longest-edge-down attempt, overlap geometry cache
- DXF layer checks through `layer_audit`
- SVG rendering from placed outlines
- Average seam-allowance rough expansion
- Separate `minimum_yield` and `quote_yield`
- `allowance_policy` quote buffer and confidence output
- DXF autoscale
- MCP stdio transport

Not yet supported:

- Arbitrary-angle rotation
- Full DXF entity and CAD layer convention detection
- High-precision curve flattening
- Print matching
- Commercial CAD-grade final nesting

## Development

```powershell
python -m unittest discover -s tests
```

## License

This project is source-available under the **PolyForm Noncommercial License 1.0.0**.

You may use, study, modify, and share it for noncommercial purposes under the license terms.

Commercial use, production use, paid consulting, resale, hosted service use, or integration into commercial workflows requires a separate written commercial license from the copyright holder.

- [LICENSE](LICENSE)
- [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)
- [NOTICE](NOTICE)

This project is not OSI-approved open source because commercial use is restricted.
