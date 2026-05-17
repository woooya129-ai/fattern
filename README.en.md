# Fattern

[한국어](README.md)

A CLI/MCP tool for fast rough marker-yield estimation from DXF garment pattern files.

Fattern means **FAST + PATTERN = FATTERN**.

This repository is **source-available, noncommercial use only** under **PolyForm Noncommercial License 1.0.0 + a separate Commercial License**.

## One-Line Use

Put one DXF file and `answers.json` in `input/`, then run:

```powershell
python -m fattern estimate
```

You can also pass options directly:

```powershell
python -m fattern estimate input\sample.dxf --fabric-width 150 --unit cm --dxf-unit auto --grainline-status unknown --seam-allowance-included no --one-way-fabric no --rotation 0
```

Results are written to `output/YYYYMMDD-HHMMSS_DXFNAME/`.

```text
output/
  20260517-223500_Simple-T/
    marker_preview.svg
    marker_report.md
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
  "fabric_width": 150,
  "unit": "cm",
  "dxf_unit_hint": "auto",
  "grainline_status": "unknown",
  "seam_allowance_included": "no",
  "one_way_fabric": "no",
  "rotation_allowed_degrees": [0],
  "clearance": 0.2
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
- `dxf_unit_hint`: DXF coordinate unit, usually `auto`
- `grainline_status`: `present`, `missing`, or `unknown`
- `seam_allowance_included`: whether seam allowance is already included
- `seam_allowance_width`: average seam allowance if missing
- `one_way_fabric`: whether the fabric is directional
- `rotation_allowed_degrees`: allowed rotations, default `[0]`
- `clearance`: spacing between pieces

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

For one-way fabric, `grainline_status=missing` blocks layout. Fix the DXF grainline information or confirm the status before continuing.

See [docs/marker-rules.md](docs/marker-rules.md) for detailed marker rules.

## Seam Allowance Defaults

When seam allowance is not included, set `seam_allowance_included` to `no`. Fattern applies a rough average allowance.

- `mm`: `10.0`
- `cm`: `1.0`
- `m`: `0.01`
- `inch`: `0.375`
- `ft`: `0.03125`
- `yd`: `0.0104167`

This is a rough expansion, not an exact CAD offset-curve operation.

## DXF Unit Autoscale

The default is `--dxf-unit auto`. Fattern compares candidate units against garment-pattern size and fabric-width context.

If the drawing is ambiguous, pass a unit explicitly.

```powershell
python -m fattern estimate input\sample.dxf --fabric-width 150 --unit cm --dxf-unit mm --grainline-status unknown --seam-allowance-included yes --one-way-fabric no
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
