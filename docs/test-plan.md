# Test Plan

## Scope

```text
P1 schema contract
P2 engine core
P3 MCP wrapper
P4 orchestration regression
P5 SVG/report
```

## P1 Schema Tests

```text
test_schema_files_are_valid_json_objects
  - 모든 schemas/*.schema.json이 JSON object인지 확인
  - $schema가 draft 2020-12인지 확인

test_llm_facing_schemas_are_closed
  - UserIntent와 Clarification이 additionalProperties false인지 확인
  - schema_version const 1.0 확인

test_policy_defaults_are_locked
  - unit default cm
  - rotation default 0, 180
  - clearance default 0.2
  - seam_allowance_included default null

test_opaque_id_pattern_blocks_paths
  - job_abc-123 허용
  - layout_marker_1 허용
  - ../outside 차단
  - C:/outside 차단

test_mcp_tool_contracts_are_closed
  - 정의된 input schema의 additionalProperties false 확인
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

Geometry metrics
  - rectangle bbox width and height
  - rectangle area
  - triangle area
  - perimeter
  - self-intersection returns SELF_INTERSECTION blocker
  - area <= 0 returns INVALID_POLYGON blocker

Layout
  - two pieces fit within fabric width
  - fabric width overflow moves to next row
  - compact layout reuses gaps above shorter pieces
  - compact layout tries larger-piece ordering to reduce marker length
  - layout candidate search evaluates edge-aligned and 1x/2x clearance-contact positions
  - detailed search is compared against bbox baseline and cannot return a worse marker length
  - local compaction pass reinserts pieces into lower valid positions
  - polygon collision checks use edge bounding-box pruning before exact segment tests
  - polygon-aware layout nests pieces into concave gaps when outlines do not overlap
  - rotation not allowed is respected
  - clearance 0.2cm is applied
  - marker_length is deterministic
  - efficiency is deterministic
  - overlap returns OVERLAP_DETECTED
```

## P3 MCP Tests

```text
Tool discovery
  - tools/list exposes expected tools
  - each tool has inputSchema
  - schema names match queue contract

Transport
  - stdio initialize returns tools capability
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
  - create_job returns opaque job_id only
  - register_input_file accepts file_name + content_base64 and returns file_id
  - parse_dxf accepts file_id, not path
  - extract_pattern_pieces returns piece_set_id
  - calculate_piece_metrics returns metrics_id and metrics
  - estimate_marker_layout returns layout_id and validity
  - render_marker_svg returns artifact id, not absolute path
  - get_job_status does not leak another job
  - export_artifacts uses manifest allowlist
```

## P4 Orchestration Regression

```text
Missing input
  - no DXF file asks for file
  - no fabric width asks for fabric width
  - unknown unit asks for unit

Tool chain
  - create_job -> register_input_file -> parse_dxf -> extract_pattern_pieces -> calculate_piece_metrics -> estimate_marker_layout -> render_marker_svg
  - blocker after parse_dxf stops chain
  - blocker after extract_pattern_pieces stops chain
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
  - viewBox ratio uses fabric_width and marker_length
  - fabric boundary rect exists
  - piece polygon outline count matches placements when outline points are available
  - renderer falls back to bbox rectangles when outline points are unavailable
  - piece label count matches placements
  - missing grainline warning has data-warning
  - script is absent
  - foreignObject is absent
  - external href is absent

Markdown report
  - numbers match result JSON
  - warning section exists
  - excluded pieces section exists
  - user text is escaped
  - internal absolute paths are absent
```

## Required Commands

```text
python -m unittest tests/test_schemas.py
python -m unittest discover -s tests
```

`pytest`는 현재 환경에 없으므로 선택 명령이다.

```text
pytest
```
