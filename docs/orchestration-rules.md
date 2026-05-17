# Orchestration Rules

## ORCH-001 Boundary

- `UserIntent`는 사용자 입력을 `schemas/user-intent.schema.json` 계약에 맞게 정규화한다.
- `file_id` 또는 `dxf_file`은 입력 판정에만 사용하고 `UserIntent` 출력에는 넣지 않는다.
- `file_id`는 `file_` prefix opaque ID일 때만 DXF 파일 참조로 인정한다.
- 파일 참조가 없으면 `missing_fields`에 `dxf_file`을 넣는다.
- `fabric_width`, `unit`, `seam_allowance_included`, `one_way_fabric`이 없거나 알 수 없으면 `missing_fields`에 넣는다.
- `grainline_status`는 `rules` 안에 `present`, `missing`, `unknown`으로 정규화한다.
- `ClarificationRequest`는 `missing_fields`가 있을 때만 만들고 `schemas/clarification.schema.json` 계약에 맞춘다.
- 사용자가 intent를 지정하지 않았고 `missing_fields`가 있으면 intent는 `ask_clarification`으로 둔다.

## Defaults

- 회전 규칙이 없거나 유효하지 않으면 `[0]`을 쓴다.
- 식서 확인 여부가 없거나 유효하지 않으면 `unknown`을 쓴다.
- clearance가 없거나 유효하지 않으면 `0.2`를 쓴다.
- `unit`은 누락 시 스키마 기본값을 자동 적용하지 않고 `null`로 둔다. 결과와 원단 폭 단위는 사용자 확인이 필요하다.
- `dxf_unit_hint`는 기본값 `auto`를 쓴다. DXF 좌표 단위는 계산 tool에서 의류 패턴 크기와 원단 폭 기준으로 추정한다.

## ORCH-002 Boundary

- MCP tool chain 실행은 ORCH-002 범위다.
- 호출 순서는 `create_job -> register_input_file -> parse_dxf -> extract_pattern_pieces -> calculate_piece_metrics -> estimate_marker_layout -> render_marker_svg`다.
- `register_input_file`은 경로가 아니라 `file_name`과 `content_base64`만 받는다.
- tool 응답의 `errors`에 `severity=blocker`가 있으면 다음 계산 tool을 호출하지 않는다.
- `estimate_marker_layout`에는 사용자 `grainline_status`가 `present` 또는 `missing`이면 그 값을 우선 넘긴다. 아니면 추출 결과로 판단한다.

## Product Invariants

- DXF 좌표, 면적, bbox, marker_length, efficiency를 LLM이 직접 계산하지 않는다.
- SVG path를 직접 만들지 않는다.
- tool output에 없는 피스명을 만들지 않는다.
- blocker 이후 다음 계산 tool 호출을 허용하지 않는다.

## ORCH-040 High-Level Adapter

- `calculate_marker_yield` 고수준 요청은 schema/MCP 계약이 확정되기 전까지 orchestration helper에서만 기존 `UserIntent`로 변환한다.
- `cuttable_width`가 있으면 `fabric_width`보다 우선해서 `fabric.width`로 넘긴다.
- `spacing`은 기존 `rules.clearance`로 넘긴다. 근거는 둘 다 선택 단위 기준 피스 간 최소 간격을 뜻하기 때문이다.
- `nap_direction=one_way`는 `rules.one_way_fabric=true`로 넘긴다.
- `nap_direction`이 `none`, `two_way`, `no_nap`, `not_one_way`이면 `rules.one_way_fabric=false`로 넘긴다.
- `pattern_file_id`만으로는 현재 orchestration layer가 기존 job/file mapping을 복원할 수 없다. 업로드 파일명과 content가 없으면 `PATTERN_FILE_MAPPING_UNRESOLVED` blocker로 중단한다.
- `size_ratio`, `piece_quantity`, `fabric_type`, `shrinkage_percent`, `shrinkage`는 고수준 `calculate_marker_yield` 경로에서 직접 처리한다. 기존 `UserIntent` adapter가 안전하게 매핑할 수 없는 경우에는 임의로 무시하지 않고 blocker로 중단한다.
- `grainline_required=true`는 `estimate_marker_layout`에 그대로 넘기고, 추출 결과 grainline이 missing이면 layout policy에서 blocker로 중단한다.
- `grainline_required`와 `nap_direction`은 직교 조건이다. `nap_direction`은 회전 정책으로만 다룬다.
- adapter blocker는 `stopped_at=adapt_marker_yield_request`, `tool_calls=[]`를 반환한다.
