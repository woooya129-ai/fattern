# Fattern

[한국어](README.md)

A CLI/MCP tool for fast rough marker-yield estimation from DXF garment pattern files.

Fattern means **FAST + PATTERN = FATTERN**.

Current version: **0.7.0**

This repository is **source-available, noncommercial use only** under **PolyForm Noncommercial License 1.0.0 + a separate Commercial License**.

## Quick Understanding

- Fattern is not an LLM calculator. It is a **DXF-based deterministic marker yield engine**.
- Inputs are a DXF pattern and fabric conditions. Outputs are rough marker estimate artifacts.
- Main artifacts are `result.json`, `marker_preview.svg`, `marker_report.md`, `marker_report.pdf`, and `report.csv`.
- v0.7.0 supports CSV/PDF reports, canonical `answers.json`, and the high-level MCP tool `calculate_marker_yield`.
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
  "seam_allowance": {"status": "included"}
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

When seam allowance is not included, set `seam_allowance` to `{"status": "excluded"}`. If `fallback_width` is absent, Fattern applies a rough average allowance for the selected unit.

- `mm`: `10.0`
- `cm`: `1.0`
- `m`: `0.01`
- `inch`: `0.375`
- `ft`: `0.03125`
- `yd`: `0.0104167`

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

If an MCP client exposes prompts in a slash UI, `/fattern-help` and `/fattern-estimate` can appear there. This depends on client support. The server supports `prompts/list` and `prompts/get`.

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
- Bbox baseline + polygon-aware compact rough marker layout
- SVG rendering from placed outlines
- Average seam-allowance rough expansion
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
