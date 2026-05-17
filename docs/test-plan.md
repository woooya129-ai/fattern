# Test Plan

## Scope

```text
P1 schema contract
P2 engine core
P3 MCP wrapper and stdio
P4 orchestration regression
P5 SVG/report
P6 CLI workflow
P7 repository hygiene
```

## P1 Schema Tests

```text
test_schema_files_are_valid_json_objects
  - schemas/*.schema.json이 JSON object인지 확인
  - $schema가 draft 2020-12인지 확인

test_llm_facing_schemas_are_closed
  - UserIntent와 ClarificationRequest가 additionalProperties false인지 확인
  - schema_version const 1.0 확인

test_policy_defaults_are_locked
  - unit default cm
  - dxf_unit_hint default auto
  - grainline_status default unknown
  - rotation default [0]
  - clearance default 0.2
  - seam_allowance_included default null
  - seam_allowance_width default null

test_opaque_id_pattern_blocks_paths
  - job_abc-123 허용
  - layout_marker_1 허용
  - ../outside 차단
  - C:/outside 차단

test_mcp_tool_contracts_are_closed
  - 정의된 input schema가 additionalProperties false인지 확인
```

## P2 Engine Tests

```text
DXF parser
  - empty file returns PARSE_FAILED or standard blocker
  - malformed DXF returns PARSE_FAILED
  - LWPOLYLINE rectangle returns one closed candidate
  - R12 POLYLINE rectangle returns one closed candidate
  - non-closed contour returns NON_CLOSED_CONTOUR or excluded piece
  - unsupported DXF returns UNSUPPORTED_DXF_VERSION
  - LINE entities are separated from piece geometry for grainline/internal-line policy
  - TEXT/MTEXT entities are treated as untrusted annotation and excluded from geometry

Geometry metrics
  - rectangle bbox width and height
  - rectangle area
  - triangle area
  - perimeter
  - auto DXF unit scales coordinates to requested output unit
  - mm, cm, m, inch, ft, yd unit candidates are accepted
  - average seam allowance expands bbox, area, and perimeter
  - average seam allowance emits SEAM_ALLOWANCE_ESTIMATED warning
  - self-intersection returns SELF_INTERSECTION blocker
  - area <= 0 returns INVALID_POLYGON blocker

Layout
  - two pieces fit within fabric width
  - fabric width overflow moves to next row
  - compact layout reuses gaps above shorter pieces
  - layout tries larger and harder piece ordering
  - detailed search is compared against bbox baseline and cannot return a worse marker length
  - local compaction pass reinserts pieces into lower valid positions
  - polygon collision checks use edge bbox pruning before exact segment tests
  - polygon-aware layout nests pieces into available outline gaps when valid
  - rotation not allowed is respected
  - clearance is applied
  - marker_length and efficiency are deterministic
  - overlap returns OVERLAP_DETECTED
```

## P3 MCP Tests

```text
Tool discovery
  - tools/list exposes expected tools
  - get_estimation_questionnaire exposes setup questions and fabric width presets
  - each tool has inputSchema
  - schema names match queue contract

Prompt discovery
  - prompts/list exposes fattern-help and fattern-estimate
  - prompts/get returns workflow help

Transport
  - stdio initialize returns tools and prompts capabilities
  - stdio tools/list returns tool definitions
  - stdio tools/call wraps structuredContent and isError
  - stdout contains only JSON-RPC messages

Validation
  - unknown fields return TOOL_VALIDATION_FAILED
  - invalid unit returns TOOL_VALIDATION_FAILED
  - invalid opaque ID returns blocker

Workspace security
  - absolute path input is rejected
  - relative path traversal is rejected
  - UNC path is rejected
  - Windows drive letter path is rejected
  - ADS syntax is rejected
  - symlink or junction escape is rejected

Wrappers
  - get_estimation_questionnaire returns canonical answers fields: fabric_width, unit, size_ratio, spacing, allowed_rotation, grainline_required, nap_direction, shrinkage_percent, fabric_type, seam_allowance
  - create_job returns opaque job_id only
  - register_input_file accepts file_name + content_base64 and returns file_id
  - parse_dxf accepts file_id, not path
  - extract_pattern_pieces returns piece_set_id
  - calculate_piece_metrics returns metrics_id and metrics
  - estimate_marker_layout returns layout_id, grainline_status, one_way_fabric, and validity
  - render_marker_svg returns artifact id, not absolute path
  - get_job_status does not leak another job
  - export_artifacts uses manifest allowlist
  - calculate_marker_yield returns result JSON, SVG, CSV, Markdown, and PDF artifact IDs
```

## P4 Orchestration Regression

```text
Missing input
  - no DXF file asks for file
  - no fabric width asks for fabric width
  - unknown unit asks for unit

Tool chain
  - create_job -> register_input_file -> parse_dxf -> extract_pattern_pieces -> calculate_piece_metrics -> estimate_marker_layout -> render_marker_svg
  - calculate_piece_metrics receives dxf_unit_hint=auto and fabric width context
  - calculate_piece_metrics receives seam_allowance_width when seam_allowance_included=false
  - estimate_marker_layout receives explicit grainline_status when user provided it
  - blocker after parse_dxf stops chain
  - blocker after extract_pattern_pieces stops chain
  - blocker after missing grainline on one-way fabric stops at layout
  - SVG_RENDER_FAILED warning still returns JSON result

Hallucination guard
  - final report does not invent marker_length
  - final report does not invent efficiency
  - final report does not invent piece names
  - final report does not say 확정 요척
  - final report labels result as rough marker or 가요척
```

## P5 SVG/Report Tests

```text
SVG
  - viewBox includes fabric area and side information panel
  - fabric boundary rect exists
  - piece polygon outline count matches placements when outline points are available
  - renderer falls back to bbox rectangles when outline points are unavailable
  - piece label count matches placements
  - fabric width, marker length, grainline status, and rotation text are present
  - grainline direction line and arrow are present
  - missing grainline warning has data-warning
  - script is absent
  - foreignObject is absent
  - external href is absent

Markdown report
  - numbers match result JSON
  - grainline_status, one_way_fabric, and rotation_allowed_degrees are present
  - warning section exists
  - excluded pieces section exists
  - user text is escaped
  - internal absolute paths are absent

PDF report
  - marker_report.pdf has a valid PDF header
  - PDF text is escaped before entering the PDF stream
```

## P6 CLI Workflow

```text
CLI
  - python -m fattern questionnaire returns valid JSON
  - python -m fattern estimate can use explicit DXF path and flags
  - python -m fattern estimate can use input/ plus answers.json
  - output directory uses YYYYMMDD-HHMMSS_DXFNAME
  - marker_preview.svg, marker_report.md, marker_report.pdf, result.json, report.csv are copied to the run output directory
  - missing required answers return needs_clarification details
```

## P7 Repository Hygiene

```text
Repository hygiene
  - tracked root files stay inside the explicit allowlist
  - AI working files and generated output are not tracked
  - .gitignore contains required local-only patterns
```

## Required Commands

```text
python -m unittest tests/test_schemas.py
python -m unittest tests.test_repository_hygiene
python -m unittest discover -s tests
```

`pytest`는 현재 필수 명령이 아니다.
