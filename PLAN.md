# Fattern PLAN

## 제품 방향

Fattern은 `LLM 가요척 계산기`가 아니다.

Fattern의 제품 정의는 **DXF 기반 deterministic marker yield engine + 견적용 가요척 의사결정 레이어 + LLM 오케스트레이터**다.

LLM은 계산 주체가 아니라 작업 지시자다. 사용자 입력을 정리하고, 필요한 질문을 만들고, MCP tool 호출 순서를 제어하고, blocker를 판단하고, tool output을 사람이 읽기 쉬운 결과로 설명한다.

Engine은 계산 주체다. DXF/AAMA/ASTM 파싱, polygon 추출, grainline, seam allowance, 수량 조건 처리, nesting, marker length, utilization, waste 계산, SVG/CSV/PDF 출력을 담당한다. Quote layer는 engine의 최소 소요량에 실무 견적용 allowance, rounding, warning risk, confidence를 얹는다.

## 현재 완료 상태

- 릴리스 표기: `pyproject.toml`, `README.md`, `README.en.md` 기준 `0.9.0`으로 정리 완료.
- 빠른 이해와 설치 문서: README 양쪽에 빠른 이해, 설치 방법, 실행 예시, 산출물 목록 반영 완료.
- 고수준 경로: `calculate_marker_yield`, CLI `estimate`, canonical `answers.json` 연동 완료.
- 조건 엔진: `cuttable_width`, `size_ratio`, `piece_quantity`, `spacing`, `nap_direction`, `fabric_type`, `shrinkage`, `stretch_direction`, `seam_allowance` 정책 반영 완료.
- blocker 정책: cuttable width 초과, one-way 180 회전, woven/grainline required/one-way grainline missing, invalid nap, invalid shrinkage, invalid seam fallback 차단 완료.
- DXF 의미 분리: `LINE`은 grainline 후보 또는 internal line으로 분리하고, `TEXT`/`MTEXT`는 annotation으로 제외 완료.
- DXF layer audit: `parse_dxf`와 `extract_pattern_pieces` 응답에 layer별 entity count, grainline candidate source, confidence, mapping status 노출 완료.
- DXF 수용성: ACAD version 미검증값은 blocker 대신 warning으로 처리하고, legacy `POLYLINE + VERTEX + SEQEND`와 연결된 `LINE` 폐곡선 후보를 piece로 수용 완료.
- Nesting 개선: shelf compact 보조 step, longest-edge-down attempt, overlap geometry cache 반영 완료.
- 리포트 산출물: `result.json`, `marker_preview.svg`, `marker_report.md`, `marker_report.pdf`, `report.csv`, 별도 zip export 경로 완료.
- 견적용 가요척: `minimum_yield`, `quote_yield`, `allowance_breakdown`, `confidence` 출력 완료.
- 접근성: `fattern` 기본 실행 Web UI 자동 오픈, 로컬 Web UI, MCP, CLI 계약 유지 완료.
- run 저장 계약: Web UI/CLI/MCP high-level 결과를 `output/run_id/`로 저장하고 `run_summary.txt`, `web_url`, `preview_url`, `report_url`을 노출 완료.
- Advisor: LLM 없는 deterministic Advisor와 선택형 서버-side LLM Advisor 추가 완료.
- 계약 정리: LLM-facing schema, MCP tool schema, README 예시, 테스트 계약 동기화 완료.
- Hosted 준비: `fattern host`, `/mcp`, `/hosting/policy`, `/server.json`, `/healthz` 추가 완료.
- 검수 기준: `python -m unittest discover -s tests` 기준 191 tests OK, 1 skipped.

## 역할 경계

### LLM 역할

- 질문지 생성
- 사용자 답변 정리
- MCP tool 호출 순서 제어
- blocker 판단
- warning과 결과 설명
- tool output 기반 report 요약

### LLM 금지 추론

- DXF layer convention을 추론하지 않는다. AAMA/ASTM 여부는 engine의 파일 header, layer rule, parser output만 신뢰한다.
- piece grading group을 추론하지 않는다. piece name/size 패턴 매칭은 engine에서 deterministic하게 처리한다.
- 사이즈 라벨 의미를 추론하지 않는다. `S-M-L`, `36-38-40`, `1-2-3` 같은 체계는 사용자 입력 또는 DXF metadata가 있을 때만 사용한다.
- shrinkage 방향을 추론하지 않는다. warp/weft, 길이/폭 방향은 사용자 입력 또는 DXF의 명시값만 사용한다.
- fabric type을 파일명이나 layer명으로 추정하지 않는다. 사용자가 명시하지 않으면 `unknown`이다.
- 회전 정책을 임의 변경하지 않는다. 회전은 사용자 입력 `allowed_rotation` 안에서만 engine이 시도한다.
- piece 면적, 좌표, bbox, marker length, utilization, waste를 직접 계산하지 않는다.

### Engine 역할

- DXF/AAMA/ASTM 파싱
- polygon 추출
- grainline 처리
- seam allowance 처리
- piece quantity와 size ratio 반영
- nesting
- marker length 계산
- utilization 계산
- waste 계산
- SVG, CSV, PDF 출력

## 핵심 제품 원칙

- LLM은 숫자 계산을 하지 않는다.
- 모든 숫자는 tool output을 기준으로 한다.
- 내부 기준 단위는 `mm`로 통일한다.
- 사용자는 `cm`, `inch`, `ft`, `yd`, `mm`로 입력할 수 있다.
- 식서 방향은 기본 고정이다.
- 회전 기본값은 `[0]`이다.
- 식서 미확인 상태에서 원웨이 원단이면 blocker다.
- `fabric_width`보다 `cuttable_width`가 있으면 `cuttable_width`를 우선한다.
- `cuttable_width > fabric_width`이면 `INVALID_CUTTABLE_WIDTH` blocker로 중단한다.
- `grainline_required`와 `nap_direction`은 직교 조건이다.
- `fabric_type=woven` 또는 `grainline_required=true`이면 grainline missing은 nap direction과 무관하게 blocker다.
- `nap_direction=one_way`이면 `180` 회전을 자동 허용하지 않는다.
- `fabric_type=woven`이면 grainline을 엄격히 본다.
- blocker error 이후 다음 계산 tool을 호출하지 않는다.

## v0.4.0 목표: 고수준 MCP Tool

목표는 사용자가 한 번에 호출할 수 있는 고수준 tool을 제공하는 것이다.

```text
calculate_marker_yield
```

외부 입력은 단순하게 유지한다.

```json
{
  "pattern_file_id": "file_xxx",
  "fabric_width": 1470,
  "cuttable_width": 1450,
  "unit": "mm",
  "size_ratio": {"S": 1, "M": 2, "L": 2, "XL": 1},
  "piece_quantity": {"piece_0001": 2},
  "spacing": 5,
  "allowed_rotation": [0],
  "grainline_required": true,
  "nap_direction": "one_way",
  "shrinkage_percent": 3,
  "shrinkage": {
    "length_percent": 3,
    "width_percent": 0
  },
  "fabric_type": "woven",
  "seam_allowance": {
    "status": "included",
    "fallback_width": 10
  }
}
```

내부에서는 기존 tool chain을 호출한다.

```text
create_job
register_input_file
parse_dxf
extract_pattern_pieces
calculate_piece_metrics
estimate_marker_layout
render_marker_svg
export_artifacts
```

각 단계에서 `errors`에 `severity=blocker`가 있으면 즉시 중단한다. 중단 이후의 계산 tool은 호출하지 않는다.

### v0.4.0 작업

- `calculate_marker_yield` MCP schema 추가 (완료)
- Python tool schema와 JSON schema 동기화 (완료)
- CLI에서 같은 request 구조 사용 (완료)
- `input/answers.json`을 `calculate_marker_yield` request와 최대한 유사하게 정리 (완료: canonical answers schema 추가)
- `size_ratio`는 base size 복제 모델로 반영하고 `SIZE_RATIO_BASE_SIZE_REPLICATED` warning을 남긴다. (완료)
- `cuttable_width > fabric_width`, grainline/nap 직교 정책, shrinkage 적용 가능 조건을 schema와 engine policy에 반영한다. (완료)
- 기존 tool chain을 감싸는 orchestration wrapper 구현 (완료: `McpToolRegistry._calculate_marker_yield`)
- blocker 발생 시 partial result와 중단 이유 반환 (완료)
- `export_artifacts`에 `result.json`, `marker_preview.svg`, `marker_report.md`, `marker_report.pdf`, `report.csv` 포함 (완료: artifact ID 반환과 별도 zip export 경로 검증)
- `nap_direction=one_way` + grainline missing 정책 enforcement (완료)

### v0.4.0 DoD

- `calculate_marker_yield` schema가 추가되어 있다. (완료)
- CLI와 MCP가 같은 request 구조를 사용한다. (완료)
- `input/answers.json` 구조가 고수준 request와 크게 다르지 않다. (완료)
- output에 아래 파일이 생성된다. (완료)

```text
result.json
marker_preview.svg
marker_report.md
marker_report.pdf
report.csv
```

- blocker 발생 시 중간 산출물과 이유가 명확히 표시된다. (완료)
- blocker 이후 다음 계산 tool이 호출되지 않는다. (완료)
- tool output 숫자와 report 숫자가 일치한다. (완료: `validate_final_report`로 검증)
- path traversal 방어가 유지된다. (완료)
- warning이 report에 표시된다. (완료)

### v0.4.0 result.json 계약

`result.json` artifact에는 아래 키가 항상 포함되어야 한다.

```text
status (completed | blocked)
stopped_at
tool_calls
warnings
errors
job_id
pattern_file_id
artifact_ids
```

happy path에서는 추가로 `layout`, `layout_id`, `metrics_id`, `dxf_parse_id`, `piece_set_id`, `dxf_unit`, `unit_scale`, `export_artifact_ids`, `partial_csv_fields`가 포함된다.

blocked path에서는 도달한 단계까지의 `dxf_parse_id`, `piece_set_id`, `metrics_id`, `layout_id`, `layout` 키만 추가로 포함된다.

### v0.4.0-v0.6.0 grainline 자동 감지 상태

현재 `extract_pattern_pieces`는 DXF `LINE` entity를 기준으로 piece별 grainline 후보를 감지한다. 명시 `grainline_layer_names`가 있으면 그 layer를 우선하고, 없으면 deterministic layer rule만 후보로 둔다.

- piece 안에 grainline line midpoint가 있으면 `has_grainline=true`, `grainline_status=present`.
- 후보 rule로 감지된 경우 confidence와 warning을 함께 반환한다.
- piece-level grainline이 없고 `grainline_required=True`이면 `MISSING_GRAINLINE_REQUIRED` blocker.
- piece-level grainline이 없고 `fabric_type=woven`이면 `MISSING_GRAINLINE_FOR_WOVEN` blocker.
- piece-level grainline이 없고 `nap_direction=one_way`이면 `MISSING_GRAINLINE_ON_ONE_WAY_FABRIC` blocker.

자동 감지는 오탐 가능성이 있으므로 생산 확정용으로 쓰면 안 된다.

### v0.4.0 export 정책

`calculate_marker_yield`는 `export_artifact_ids` 리스트만 반환한다. 실제 zip은 클라이언트가 `export_artifacts`를 별도 호출해서 생성한다. 이 별도 호출 방식은 확정 정책이며 완료 상태다.

`calculate_marker_yield` 내부에서 자동 zip까지 생성하는 동작은 의도적으로 범위 밖이다. 회귀 테스트는 exportable artifact ID 반환과 별도 zip 생성 경로를 검증한다. (완료)

### v0.4.0 테스트

- happy path (완료: `test_calculate_marker_yield_happy_path_returns_exportable_artifacts`)
- missing grainline (완료: `test_calculate_marker_yield_stops_on_blocker_without_following_tools`)
- invalid rotation (완료: schema validation)
- `cuttable_width` 우선 (완료: `test_estimate_marker_layout_applies_cuttable_spacing_and_nap_policy`)
- `cuttable_width > fabric_width` blocker (완료: `test_calculate_marker_yield_rejects_cuttable_width_larger_than_fabric_width`)
- one-way fabric + `allowed_rotation=[0, 180]` 입력 시 180 차단 (완료: `test_calculate_marker_yield_blocks_one_way_180_rotation_before_chain`)
- woven + grainline missing이 nap direction과 무관하게 blocker (완료: `test_calculate_marker_yield_blocks_woven_without_grainline_before_metrics`)
- DXF에 closed polyline이 하나도 없으면 extract 단계 blocker (완료: engine 레벨에서 `NO_PATTERN_PIECES_FOUND`)
- 단일 piece bbox가 fabric width를 초과하면 `FABRIC_WIDTH_EXCEEDED` (완료: `test_estimate_marker_layout_does_not_store_blocked_layout`)
- seam allowance `fallback_width` 음수 blocker (완료: `test_calculate_marker_yield_rejects_negative_seam_allowance_fallback`)
- shrinkage percent가 100 이상이면 blocker (완료: `test_calculate_marker_yield_rejects_shrinkage_percent_at_100`)
- `size_ratio`는 base size 복제 모델로 반영한다. grading 차이는 추론하지 않고 `SIZE_RATIO_BASE_SIZE_REPLICATED` warning으로 표시한다.
- `nap_direction=one_way` + grainline missing이 `grainline_required=False` + `fabric_type=unknown` 조합에서도 blocker (완료)
- CLI 경로에서도 `result.json`, `report.csv`, `marker_report.pdf`가 생성되어야 한다는 회귀 테스트 (완료)

## v0.5.0 목표: 의류 조건 엔진

v0.5.0은 marker yield 계산에 필요한 의류 조건을 명시적 schema와 engine policy로 끌어올리는 단계다.

추가 또는 정교화할 조건은 아래와 같다.

- `cuttable_width`
- `size_ratio`
- `piece_quantity`
- `shrinkage_percent`
- `spacing`
- `nap_direction`
- `fabric_type`
- `seam_allowance.status`

### v0.5.0 정책

- `nap_direction=one_way`이면 `180`을 자동 허용하지 않는다.
- `fabric_type=woven`이면 grainline을 엄격히 검증한다.
- `fabric_type=knit`이면 `stretch_direction` 입력을 받되 stretch matching은 적용하지 않고 warning으로 노출한다. (완료)
- shrinkage는 길이 방향과 폭 방향을 나눌 수 있게 설계한다. (완료)
- `spacing`은 piece 간 최소 간격으로 해석한다. (완료)
- `size_ratio`는 base size 복제 모델로 반영한다. graded DXF 모델은 명시 metadata가 있을 때만 제한적으로 사용한다. (완료)
- `piece_quantity`는 DXF 또는 사용자 입력에서 온 수량 조건으로 분리한다. (완료)
- `grainline_required`는 `nap_direction`과 독립된 조건이다. (완료)
- woven 원단에서 grainline이 missing이면 nap direction과 무관하게 blocker다. (완료)
- `nap_direction`은 회전 허용값에만 영향을 준다. `one_way`에서는 180 회전을 차단한다. (완료)
- `cuttable_width > fabric_width`는 blocker다. (완료)

현재 구현 상태:

- `piece_quantity`는 piece id 또는 `*` 키 기준으로 base outline을 복제한다. (완료)
- `size_ratio`와 `piece_quantity`가 함께 있으면 두 수량 조건을 곱해 복제한다. (완료)
- `shrinkage_percent`와 `shrinkage.length_percent/width_percent`를 지원한다. (완료)
- piece-level grainline이 있으면 grainline 축/직교 축 기준으로 shrinkage를 적용한다. (완료)
- piece-level grainline이 없으면 shrinkage를 적용하지 않고 warning을 반환한다. (완료)
- `fabric_type=knit`은 `stretch_direction` 입력을 받는다. 현재 marker engine은 stretch matching을 적용하지 않고 warning으로 노출한다. (완료)

### v0.5.0 설계 메모

`size_ratio`에서 검토했던 선택지는 아래 둘이다.

```text
graded DXF 필수:
  AAMA/ASTM piece set 안에 사이즈별 outline이 있을 때만 size_ratio를 허용한다.
  piece name과 size suffix는 engine이 deterministic하게 매칭한다.

base size 복제:
  단일 base size outline을 수량만큼 복제한다.
  grading은 무시되며 report에 경고를 표시한다.
```

현재 구현은 base size 복제 모델을 선택했다. (완료)

- 단일 base outline을 `size_ratio` 수량만큼 복제한다. (완료)
- grading 차이는 추론하지 않는다. (완료)
- grading 무시는 `SIZE_RATIO_BASE_SIZE_REPLICATED` warning으로 표시한다. (완료)
- CSV에는 복제된 placement별 `size`와 `quantity=1`을 채운다. (완료)
- graded DXF size suffix 매칭은 explicit layer metadata(`piece=...;size=...`)가 있을 때만 사용한다. 일반 layer name에서 의미를 추론하지 않는다. (완료)

`shrinkage_percent`는 단일 숫자 입력을 허용하되 내부 모델은 아래 구조로 확장했다. (완료)

```json
{
  "length_percent": 3,
  "width_percent": 0
}
```

shrinkage 적용 정책은 아래와 같다.

- shrinkage는 piece의 grainline 축 기준 비등방 스케일링이다. (완료)
- nesting과 metrics 계산 이전에 outline에 적용한다. (완료)
- 길이 방향은 grainline 축, 폭 방향은 grainline에 직교한 축이다. (완료)
- piece별 grainline이 없으면 shrinkage를 적용하지 않고 warning 또는 blocker를 반환한다. (완료)
- `percent >= 100`이면 scale이 무한대가 되므로 blocker다. (완료)

`seam_allowance.status`는 고수준 `calculate_marker_yield`와 canonical `answers.json` 계약에서 아래 상태만 허용한다. (완료)

```text
included
excluded
```

`unknown`은 schema-valid 상태가 아니다. 시접 포함 여부를 모르면 사용자가 `included` 또는 `excluded`로 확정해야 한다. `excluded`에서 `fallback_width`가 없으면 단위별 평균 fallback으로 rough 확장을 적용하고 warning을 남긴다. 음수 fallback은 blocker다. (완료)

v0.5 시접 범위는 아래로 한정한다.

- piece 단위 uniform fallback width까지만 자동 적용한다. (완료)
- 기본 fallback 기준은 `1/2 inch`다. 단위별 기본값은 `mm 12.7`, `cm 1.27`, `m 0.0127`, `inch 0.5`, `ft 0.0416667`, `yd 0.0138889`로 적용한다. (완료)
- 변동 시접, curve offset, notch 보존, mitre 처리는 v0.5 범위 밖이다.

## v0.6.0 목표: DXF 의미 인식 강화

v0.6.0은 DXF 내부 의미를 더 잘 읽는 단계다. 단, LLM이 좌표나 면적을 직접 해석하지 않는 원칙은 유지한다.

우선순위는 아래 순서다.

1. AAMA/ASTM layer convention 조사
2. grainline layer 후보 자동 감지
3. piece name 감지
4. size name 감지
5. annotation/text entity 처리
6. notch/internal line은 계산에서 제외하되 report에 warning 표시

### v0.6.0 리스크 제어

- grainline 자동 감지는 오탐 가능성이 크므로 confidence와 warning을 함께 반환한다.
- piece name과 size name은 tool output에 있는 값만 report에 표시한다.
- notch와 internal line은 면적과 bbox 계산에서 제외한다.
- annotation/text entity는 untrusted text로 보고 escape한다.
- AAMA/ASTM convention은 실제 샘플 다양성이 부족하면 `근거 불충분` 상태로 남긴다.
- AAMA/ASTM layer 매핑은 spec 문서로 확인된 항목만 high-confidence rule로 hardcode한다.
- 확인되지 않은 layer는 candidate로 두고 confidence와 warning을 함께 반환한다.

현재 구현 상태:

- DXF `LINE` entity를 geometry 계산에서 분리하고 grainline 후보 또는 internal line으로만 다룬다. (완료)
- 명시 `grainline_layer_names`는 confidence 1.0 grainline rule이다. (완료)
- `GRAINLINE`, `GRAIN_LINE`, `GRAIN-LINE` 등 deterministic layer name은 confidence 0.8 후보로 둔다. (완료)
- numeric layer `7`은 AAMA/ASTM 후보로만 다루며 `AAMA_ASTM_LAYER_MAPPING_UNVERIFIED` warning을 반환한다. 로컬 근거가 충분하지 않아서 high-confidence hardcode가 아니다. layer audit로 근거 확인 정보를 노출한다. (부분 완료)
- piece name/size는 explicit layer metadata 형식 `piece=Front;size=M`만 읽는다. (완료)
- `TEXT`/`MTEXT`는 untrusted annotation으로 분리하고 geometry 계산에서 제외한다. (완료)
- grainline 후보가 아닌 `LINE`은 internal line으로 제외하고 warning을 반환한다. (완료)

### v0.6.0 AAMA/ASTM 매핑 확장 힌트

numeric layer를 high-confidence rule로 hardcode하기 전 점검할 항목이다. 현재는 layer 7만 후보 + `AAMA_ASTM_LAYER_MAPPING_UNVERIFIED` warning이고, 그 외 numeric layer는 internal line으로만 처리한다.

- vendor별 layer convention이 다르다. Lectra/Modaris, Gerber AccuMark, Optitex, Tukatech, PAD System, StyleCAD는 같은 piece 의미라도 layer 번호가 다르다. AAMA/ASTM D6673 호환 export를 보장하는 것은 일부 vendor의 옵션뿐이다.
- 단일 글로벌 mapping table 대신 `--cad-vendor` 또는 request 필드 `cad_vendor`를 받아 vendor profile별로 deterministic rule을 두는 방향이 안전하다. profile이 없으면 기존처럼 candidate + warning 유지.
- 자동 vendor 탐지는 `$ACADVER`, `$DWGCODEPAGE`, 헤더 comment, `BLOCK` 이름 prefix만 신뢰한다. 자동 탐지가 적중해도 confirmation warning을 남긴다.
- vendor profile을 candidate(0.8)에서 rule(1.0)로 승격하려면 vendor당 최소 5개 fixture DXF에서 layer→의미 매핑이 ≥80% 일치해야 한다. 그 이하면 candidate 유지.
- 사용자 측 디버깅을 위해 report에 `layer_audit` 섹션 추가를 검토한다. layer별 entity 종류 수, 채택된 rule, confidence를 노출하면 사용자가 자기 DXF를 직접 라벨링할 수 있다.

현재 반영:

- `parse_dxf`와 `extract_pattern_pieces` 응답에 `layer_audit` 추가 완료.
- layer별 `entity_counts`, `grainline_rule_source`, `grainline_confidence`, `mapping_status` 노출 완료.
- numeric layer `7`은 `aama_astm_candidate_unverified`로 표시하고, high-confidence rule 승격은 보류.
- 흔히 인용되는 매핑(layer 1 piece boundary, layer 8 internal/sew line, layer 11 internal cut, layer 13 mirror, layer 14 grainline, layer 84 drill, layer 1000+ annotation)은 로컬 fixture로 검증되기 전까지는 PLAN과 코드에 hardcode하지 않는다. 인용 출처는 `docs/marker-rules.md` reference로만 둔다.
- 우선순위가 낮은 layer(mirror, drill, annotation)는 의미 매핑 전에 "계산 제외" 처리만으로도 안전성이 올라간다. 의미 식별 없이도 piece 면적·bbox에서 빠지면 결과가 보수적으로 안정된다.

## v0.7.0 목표: 리포트 제품화

v0.7.0은 계산 결과를 사용자와 다른 도구가 안정적으로 소비할 수 있게 만드는 단계다.

출력 우선순위는 아래와 같다.

1. SVG preview
2. JSON result
3. CSV report
4. Markdown report
5. PDF report

PDF report는 단일 페이지 텍스트 PDF artifact로 생성한다. JSON, CSV, Markdown이 주 계약이고 PDF는 동일 report text를 휴대용 산출물로 감싼다.

### v0.7.0 완료 항목

- 릴리스 표기 `0.7.0` 반영 완료.
- README 빠른 이해, 설치 방법, 실행 예시 반영 완료.
- `result.json`, `marker_preview.svg`, `marker_report.md`, `marker_report.pdf`, `report.csv` 산출 완료.
- CSV placement-level 필드와 `partial_csv_fields()` 계약 정리 완료.
- Markdown report와 `result.json` 숫자 일치 검증 완료.
- 단일 페이지 PDF report 생성 완료.
- `export_artifacts` 별도 호출로 zip 생성 완료.
- schema, README 예시, MCP tool 계약, 테스트 동기화 완료.

## v0.7.1 목표: DXF 입력 수용성 확대

v0.7.1은 Simple-T처럼 구형 DXF exporter에서 나온 파일을 더 많이 받아들이는 단계다. 목표는 DXF 전체 CAD 호환을 선언하는 것이 아니라, blocker를 줄이고 deterministic fallback으로 읽을 수 있는 외곽선을 늘리는 것이다.

### v0.7.1 완료 항목

- 릴리스 표기 `0.7.1` 반영 완료.
- `$ACADVER`가 검증 목록 밖이어도 `UNVERIFIED_DXF_VERSION` warning으로 낮추고 파싱을 계속한다. (완료)
- AC1009/R12 legacy `POLYLINE + VERTEX + SEQEND` 폐곡선은 piece 후보로 처리한다. (완료)
- 같은 layer의 연결된 `LINE` 조각이 닫힌 loop를 만들면 `LINE_LOOP_CONTOUR_CONNECTED` warning과 함께 piece 후보로 처리한다. (완료)
- `connect_lines`, `mixed_entities` extraction mode는 `EXTRACTION_MODE_FALLBACK` warning과 함께 deterministic closed-outline fallback을 사용한다. (완료)
- `extract_pattern_pieces` 설명을 closed LWPOLYLINE 한정에서 closed DXF outline candidates로 수정했다. (완료)
- README How to use와 지원 범위에 legacy DXF fallback 설명을 반영했다. (완료)

### v0.7.1 한계

- ARC, CIRCLE, ELLIPSE, SPLINE, HATCH를 고정밀 outline으로 변환하는 것은 아직 범위 밖이다.
- CAD vendor별 layer convention 자동 확정은 하지 않는다. `layer_audit`와 warning으로 근거만 노출한다.
- 연결된 `LINE` loop는 같은 layer 안에서 endpoint가 맞는 단순 폐곡선만 조립한다.

## v0.8.0 목표: 견적용 가요척 의사결정 레이어

v0.8.0은 marker engine의 `minimum_yield`와 견적용 `quote_yield`를 분리하는 단계다. 엔진 결과를 바로 견적 요척으로 부르지 않고, 실무 여유분과 risk buffer를 별도 레이어에서 계산한다.

### v0.8.0 완료 항목

- 릴리스 표기 `0.8.0` 반영 완료.
- `allowance_policy` schema 추가 완료.
- `calculate_marker_yield` 응답에 `minimum_yield`, `quote_yield`, `allowance_breakdown`, `allowance_reasons`, `allowance_policy`, `confidence` 추가 완료.
- `marker_report.md`에 `Quote Summary`와 `Allowance Breakdown` 섹션 추가 완료.
- warning 기반 quote risk penalty와 confidence grade A/B/C/D 산출 완료.
- 기본 quote mode는 `fast_quote`로 두고, `sample_estimate`, `bulk_precheck` mode를 지원한다. (완료)

### v0.8.0 설계 원칙

```text
Fattern engine:
이 DXF를 이 조건으로 배치하면 최소 얼마까지 나오는가?

Quote layer:
실무 견적에서는 이 최소값에 얼마를 더 얹어야 안전한가?
```

`minimum_yield`는 deterministic marker layout의 `marker_length`를 그대로 반영한다. `quote_yield`는 `base_buffer_percent`, `cutting_loss_percent`, `end_loss_length`, `fabric_defect_buffer_percent`, `unknown_risk_buffer_percent`, warning penalty, rounding을 합쳐 산출한다.

### v0.8.0 한계

- costing은 아직 범위 밖이다. 원단 단가, 발주 수량, 총 원단 금액 계산은 v0.9에서 다룬다.
- buyer/vendor별 allowance preset은 아직 없다.
- 과거 실제 marker와의 calibration은 아직 없다.
- quote layer는 생산 확정값이 아니라 견적 의사결정 보조값이다.

## v0.8.1 목표: 일반 사용자 접근성 개선

v0.8.1은 MCP/CLI 계약을 유지하면서 일반 사용자가 브라우저로 접근할 수 있는 로컬 Web UI를 추가하는 단계다.

### v0.8.1 완료 항목

- 릴리스 표기 `0.8.1` 반영 완료.
- `fattern ui` CLI command 추가 완료.
- 로컬 Web UI에서 DXF 업로드, 원단 조건 입력, 견적 모드 선택, 결과 확인, artifact 다운로드 지원 완료.
- Web UI는 업로드된 파일 bytes를 서버 내부 `JobStore`에 직접 등록하고 기존 `calculate_marker_yield`를 호출한다. (완료)
- MCP의 `register_input_file.content_base64` 계약과 CLI `estimate` 동작은 유지한다. (완료)

### base64 경계

base64는 MCP JSON-RPC tool input에서 바이너리 DXF 내용을 JSON 문자열로 안전하게 전달하기 위한 내부 전송 포맷이다. 일반 사용자용 Web UI에서는 파일 선택 업로드를 쓰므로 base64를 화면이나 README 사용 흐름에 노출하지 않는다.

### CSV 필드

```text
piece_id
piece_name
size
quantity
area_mm2
bbox_width_mm
bbox_height_mm
x_mm
y_mm
rotation
grainline_status
```

현재 채워지는 필드와 비어있는 필드는 아래와 같다.

```text
항상 채워짐: piece_id, quantity, area_mm2, bbox_width_mm, bbox_height_mm, x_mm, y_mm, rotation
explicit DXF metadata가 있으면 채워짐: piece_name, size
piece-level grainline이 감지되면 채워짐: grainline_status
```

`grainline_status`는 piece-level이다. layout-level grainline 상태는 `marker_report.md`의 Layout 섹션에도 노출된다.

`partial_csv_fields()` 함수의 반환값은 현재 코드 상태와 일치해야 한다. explicit metadata와 grainline 감지 여부에 따라 남은 빈 metadata field만 partial로 표기한다.

### 리포트 원칙

- 숫자는 tool output만 사용한다. (완료)
- report와 `result.json`의 숫자는 일치해야 한다. (완료)
- warning은 누락 없이 표시한다. (완료)
- blocker가 있으면 결과 대신 중단 사유와 partial artifact 상태를 표시한다. (완료)
- 사용자 입력, DXF layer명, piece명은 escape한다. (완료)
- SVG에는 `script`, `foreignObject`, external href, remote resource를 넣지 않는다. (완료)

## v0.8.2 목표: Web UI + MCP 투트랙 접근성 정리

v0.8.2의 목표는 일반 사용자가 CLI/MCP를 몰라도 Web UI로 바로 계산할 수 있게 만들고, Codex/Claude Code 사용자는 MCP로 같은 결과를 조작하면서 Web UI에서 시각적으로 확인할 수 있게 하는 것이다.

핵심 제품 구조는 아래로 고정한다.

```text
일반 사용자:
  fattern 실행
  -> 브라우저 자동 오픈
  -> Web UI 안내문과 질문지
  -> DXF 업로드
  -> output/run_id 산출물 확인

AI 사용 가능 사용자:
  fattern 또는 fattern ui 실행
  -> Codex/Claude Code에서 fattern MCP 연결
  -> MCP tool로 계산
  -> MCP 응답의 web_url로 Web UI 결과 확인
```

MCP와 Web UI는 별도 제품이 아니라 같은 core engine과 같은 run artifact 계약을 공유한다. LLM은 계산하지 않고, MCP tool을 호출하고 결과를 설명한다.

### v0.8.2 사용자 경험 계약

- 사용자는 기본적으로 `fattern`만 실행하면 된다.
- `fattern` 기본 동작은 Web UI 서버 실행과 브라우저 자동 오픈이다.
- 고급 CLI 계산은 `fattern estimate`로 유지한다.
- MCP stdio는 `fattern mcp-stdio` 또는 `fattern-mcp`로 유지한다.
- 첫 실행 시 `input/`, `output/`, `config/` 폴더를 자동 생성한다.
- Web UI 첫 화면에는 안내문과 질문지가 자동으로 보인다.
- Web UI 결과는 임시 `JobStore`에만 머물지 않고 `output/YYYYMMDD-HHMMSS_DXF이름/`에 저장한다.
- Web UI와 MCP 결과는 같은 `run_id`, `output_dir`, `web_url`, `preview_url` 개념을 쓴다.
- README 첫 화면의 설치/실행 안내는 GitHub zip 한 줄 설치와 `fattern` 실행 중심으로 단순화한다. PyPI 배포 후 `python -m pip install fattern`로 교체할 수 있게 표시한다.
- 개발자용 editable install, `PYTHONPATH`, 내부 MCP base64 설명은 README 하단 또는 `docs/developer.md`로 분리한다.

### v0.8.2 기본 폴더 계약

```text
fattern-workspace/
  input/
    사용자가 직접 넣는 DXF

  output/
    20260518-153012_Simple-T/
      marker_preview.svg
      marker_report.md
      marker_report.pdf
      report.csv
      result.json
      run_summary.txt

  config/
    answers.json
```

`run_summary.txt`는 일반 사용자를 위한 가장 쉬운 한글 요약이다. JSON/MCP 결과와 숫자가 달라지면 안 된다.

### v0.8.2 Web UI 첫 화면

첫 화면은 긴 설명 문서가 아니라 작업 폼이어야 한다.

```text
1. DXF 파일 업로드
2. 원단 폭 입력
3. 단위 선택
4. 실제 재단 가능 폭 선택 입력
5. 시접 포함 여부 선택
6. 원단 방향성 선택
7. 식서 필수 여부 선택
8. 견적 모드 선택
9. 계산하기
```

기본값은 아래로 둔다.

```text
fabric_width: 150
unit: cm
cuttable_width: optional
seam_allowance.status: included
fallback seam allowance: 1/2 inch
nap_direction: two_way
grainline_required: false
allowed_rotation: [0]
spacing: 0.2
allowance_policy.mode: fast_quote
```

첫 화면 안내문은 아래 의미만 짧게 전달한다.

```text
Fattern은 DXF 패턴으로 rough marker와 견적용 가요척을 계산한다.
생산 확정용 CAD nesting 대체품은 아니다.
DXF를 올리고 원단 폭만 입력하면 먼저 계산할 수 있다.
모르는 값은 기본값으로 시작할 수 있다.
```

### v0.8.2 MCP + Web UI 연결 계약

MCP high-level tool 결과에는 아래 필드를 포함한다.

```json
{
  "run_id": "20260518-153012_Simple-T",
  "output_dir": "output/20260518-153012_Simple-T",
  "web_url": "http://127.0.0.1:8765/runs/20260518-153012_Simple-T",
  "preview_url": "http://127.0.0.1:8765/runs/20260518-153012_Simple-T/marker_preview.svg",
  "report_url": "http://127.0.0.1:8765/runs/20260518-153012_Simple-T/marker_report.pdf"
}
```

MCP 자체가 Web UI 화면을 보는 기능은 아니다. MCP는 계산과 파일 생성, Web UI는 사람이 보는 확인 화면이다. Codex나 Claude Code 같은 host AI가 브라우저 확인 기능을 갖고 있으면 Web UI까지 검수할 수 있지만, Fattern MCP 계약은 `run_id`와 URL 반환까지만 보장한다.

### 병렬 작업 분해

아래 작업은 서로 다른 파트가 동시에 진행할 수 있게 나눈다.

| 작업 ID | 파트 | 담당 역할 | 내용 | 병렬 가능 | 선행 조건 | 완료 기준 |
|---|---|---|---|---|---|---|
| A1 | Product/UX | PM 또는 UX 설계 | 일반 사용자 흐름, 첫 화면 안내문, 질문지 문구 확정 | A2, A3, A4와 병렬 가능 | 없음 | Web UI copy와 필드 정의가 PLAN/README에 반영 |
| A2 | Web UI | Frontend/Web engineer | `fattern` 기본 실행, 브라우저 자동 오픈, 질문지 자동 표시 | A1, A3와 병렬 가능 | 현재 `fattern ui` | `fattern` 실행 시 Web UI가 열림 |
| A3 | Backend/Artifacts | Backend engineer | `output/run_id/` 저장, `run_summary.txt`, artifact copy API 구현 | A1, A2, A4와 병렬 가능 | 현재 `JobStore` artifact 계약 | Web UI 계산 후 output 폴더에 파일 6종 저장 |
| A4 | MCP Integration | MCP/Agent engineer | MCP 결과에 `run_id`, `web_url`, `preview_url`, `output_dir` 추가 | A1, A3와 병렬 가능 | A3의 run registry 설계 | Codex/Claude Code 응답에서 Web UI 링크 확인 |
| A5 | Workspace Path Tool | Security/backend engineer | workspace-relative DXF path tool 추가, absolute path와 `..` 차단 | A4와 병렬 가능 | workspace root 정책 확정 | MCP에서 `input/Simple-T.dxf` 같은 경로로 계산 가능 |
| A6 | Docs | Technical writer | README 첫 화면 단순화, 개발자 문서 분리, MCP 사용법 정리 | A1과 병렬 가능 | A1 copy 초안 | 일반 사용자는 설치/실행/파일 위치를 1분 안에 이해 |
| A7 | QA/Security | QA engineer | Web UI, CLI, MCP 회귀 테스트와 path/upload 보안 테스트 | A2-A5 완료 후 집중 | A2-A5 | unittest 통과, 경로 탈출/대용량 업로드 차단 |
| A8 | Release | Maintainer | 버전 표기, changelog, commit/push, smoke test | 마지막 | A2-A7 | v0.8.2 릴리스 후보 완료 |

### 병렬 실행 순서

```text
1차 병렬:
  A1 Product/UX
  A2 Web UI 기본 실행
  A3 output/run_id 저장 구조
  A6 Docs 초안

2차 병렬:
  A4 MCP 결과 URL 연결
  A5 workspace-relative DXF path tool
  A6 Docs 보강

3차:
  A7 QA/Security
  A8 Release
```

### 역할별 책임

Product/UX:

- 일반 사용자가 보는 문장과 입력 순서를 정한다.
- 기본값이 실무적으로 위험한지 판단한다.
- "생산 확정용 아님" 경고를 과하지 않게 노출한다.

Web UI engineer:

- 브라우저 자동 오픈, 첫 화면 질문지, 결과 preview를 담당한다.
- 사용자가 base64, MCP, JSON을 보지 않게 만든다.
- 모바일보다 데스크톱 작업 효율을 우선한다.

Backend engineer:

- `JobStore` 임시 artifact를 `output/run_id/`로 내보내는 저장 계약을 만든다.
- `run_summary.txt`를 `result.json`에서 생성한다.
- Web UI와 CLI가 같은 artifact 생성 경로를 쓰게 정리한다.

MCP/Agent engineer:

- MCP prompt와 tool output을 Codex/Claude Code 사용 흐름에 맞춘다.
- workspace-relative path tool을 추가하되 arbitrary local file read가 되지 않게 막는다.
- MCP 응답에 Web UI 링크를 넣는다.

Docs owner:

- README 첫 화면은 일반 사용자용으로 줄인다.
- 개발자 설치, editable install, MCP 내부 base64 설명은 별도 문서로 이동한다.
- `input/`, `output/`, `config/` 폴더 예시를 그림 없이도 이해되게 쓴다.

QA/Security:

- `fattern`, `fattern estimate`, `fattern mcp-stdio`, Web UI upload를 모두 검증한다.
- absolute path, `..`, 비 DXF 확장자, 대용량 업로드, zip slip 회귀를 테스트한다.
- `marker_report.md`, `result.json`, `run_summary.txt` 숫자 일치를 검증한다.

### v0.8.2 완료 기준

- `fattern`만 실행해도 Web UI가 열린다.
- 처음 실행하면 `input/`, `output/`, `config/`가 생성된다.
- Web UI 첫 화면에 안내문과 질문지가 자동 표시된다.
- Web UI 계산 결과가 `output/YYYYMMDD-HHMMSS_DXF이름/`에 저장된다.
- output 폴더에 `result.json`, `marker_preview.svg`, `marker_report.md`, `marker_report.pdf`, `report.csv`, `run_summary.txt`가 있다.
- MCP high-level 결과에 `web_url`, `preview_url`, `output_dir`가 포함된다.
- README 첫 설치/실행 경로에서 개발자용 설명이 제거되어 있다.
- CLI/MCP 기존 계약은 깨지지 않는다.
- 전체 테스트가 통과한다.

### v0.8.2 완료 항목

- `fattern` 단독 실행 시 Web UI 서버와 브라우저 자동 오픈 경로 구현 완료.
- `input/`, `output/`, `config/` 자동 생성과 `config/answers.json` starter 생성 완료.
- Web UI 첫 화면 안내문과 질문지 자동 표시 완료.
- Web UI/CLI/MCP run 결과를 `output/YYYYMMDD-HHMMSS_DXF이름/`에 저장 완료.
- `result.json`, `marker_preview.svg`, `marker_report.md`, `marker_report.pdf`, `report.csv`, `run_summary.txt` 산출 완료.
- MCP `estimate_workspace_dxf` 추가와 workspace-relative path containment 완료.
- MCP high-level 결과에 `run_id`, `output_dir`, `web_url`, `preview_url`, `report_url` 추가 완료.
- README 첫 화면을 일반 사용자용 설치/실행 중심으로 단순화 완료.

## v0.8.3 목표: LLM 없는 Advisor와 MCP 자연어 UX 강화

v0.8.3은 API 비용 없이도 Web UI에서 사용자가 막히지 않게 하는 단계다. 여기서 Advisor는 LLM 채팅창이 아니라 deterministic help panel이다.

### v0.8.3 작업 후보

- Web UI 오른쪽에 Advisor 패널 추가.
- warning code별 쉬운 한국어 설명 추가.
- blocker code별 해결 방법 추가.
- `cuttable_width`, `seam_allowance`, `nap_direction`, `grainline_required`, `quote_yield` 도움말 추가.
- MCP prompt `/fattern`, `/fattern-help`, `/fattern-estimate`를 Web UI 링크 흐름에 맞게 재작성.
- Codex/Claude Code용 AGENTS/CLAUDE 예시 문서 추가.

병렬 작업:

| 작업 ID | 파트 | 담당 역할 | 내용 |
|---|---|---|---|
| B1 | Advisor copy | Domain/UX | warning/blocker 한국어 설명 작성 |
| B2 | Web UI | Frontend/Web engineer | Advisor 패널과 상태별 메시지 표시 |
| B3 | MCP prompts | MCP/Agent engineer | slash prompt와 tool call 순서 개선 |
| B4 | Docs | Technical writer | Codex/Claude Code 사용 예시 문서화 |
| B5 | QA | QA engineer | blocker/warning별 화면 문구 스냅샷 검증 |

### v0.8.3 완료 항목

- Web UI Advisor 패널 추가 완료.
- warning/blocker code별 deterministic 설명과 해결 문구 추가 완료.
- `cuttable_width`, `seam_allowance`, `nap_direction`, `grainline_required`, `quote_yield` 도움말 추가 완료.
- MCP prompt를 workspace path와 Web UI URL 반환 흐름에 맞게 수정 완료.
- Codex/Claude Code 사용 예시는 `docs/ai-clients.md`로 문서화 완료.

## v0.8.4 목표: 선택형 LLM Advisor

v0.8.4는 API key가 있는 환경에서만 Web UI에 LLM Advisor를 붙이는 단계다. 일반 사용자는 LLM 없이도 계산할 수 있어야 하고, LLM은 부가 기능이어야 한다.

### v0.8.4 원칙

- 브라우저에 OpenAI/Anthropic API key를 노출하지 않는다.
- API key는 서버 환경변수에서만 읽는다.
- LLM에는 원본 DXF 전체를 기본 전송하지 않는다.
- LLM에는 `result.json`, warning/error code, report summary 중심으로 전달한다.
- LLM은 shell, arbitrary file read, arbitrary network access를 갖지 않는다.
- LLM tool은 Fattern whitelist만 호출한다.

### v0.8.4 병렬 작업

| 작업 ID | 파트 | 담당 역할 | 내용 |
|---|---|---|---|
| C1 | LLM Backend | Backend/LLM engineer | provider adapter 구조 설계, OpenAI 우선 |
| C2 | Web UI | Frontend/Web engineer | Advisor chat panel, streaming 표시, disabled state |
| C3 | Tool Policy | Security engineer | LLM tool whitelist와 prompt injection guardrail |
| C4 | Cost Control | Product/backend | 사용량 제한, rate limit, 로그 마스킹 |
| C5 | Docs | Technical writer | BYOK/hosted/server env 차이 문서화 |
| C6 | QA/Security | QA engineer | API key 미노출, 원본 DXF 미전송, prompt injection 테스트 |

### v0.8.4 완료 항목

- 서버 환경변수 기반 선택형 LLM Advisor adapter 추가 완료.
- OpenAI Responses API와 Anthropic Messages API provider adapter 추가 완료.
- 브라우저에는 API key를 노출하지 않고 `/advisor` 서버 endpoint에서만 호출하도록 구현 완료.
- LLM context는 `layout`, `minimum_yield`, `quote_yield`, `allowance_breakdown`, `confidence`, warning/error 중심으로 sanitize 완료.
- 원본 DXF bytes, artifact ID, local output path는 LLM context에서 제외 완료.
- LLM에는 shell/file/network tool을 주지 않고 고정 provider endpoint 호출만 허용 완료.

## v0.9.0 목표: Hosted Web UI와 Remote MCP 준비

v0.9.0은 로컬 설치가 어려운 사용자를 위한 hosted Web UI와, ChatGPT/Claude.ai 같은 remote MCP connector 가능성을 준비하는 단계다.

### v0.9.0 원칙

- 로컬 Web UI, CLI, stdio MCP 계약은 깨지 않는다.
- hosted Web UI와 Remote MCP는 같은 deterministic engine과 같은 `output/run_id/` 계약을 쓴다.
- Remote MCP는 local workspace를 읽지 않는다. `estimate_workspace_dxf`는 stdio/local 전용으로 둔다.
- Remote MCP 파일 입력은 `register_input_file.content_base64`를 사용한다. base64는 암호화가 아니라 JSON 전송 포맷이다.
- 공개 바인딩은 token 없이는 막는다.
- v0.9.0은 production OAuth connector가 아니라 준비 단계다.

### v0.9.0 구현 항목

- `fattern host` 명령 추가. (완료)
- hosted-prep Web UI에서 `/mcp` HTTP JSON-RPC endpoint 제공. (완료)
- `/mcp`는 `POST` JSON-RPC를 받고 `GET`은 SSE 미구현으로 `405` 반환. (완료)
- `/hosting/policy`에서 업로드 한도, 보관 정책, 인증 상태, production blocker를 JSON으로 노출. (완료)
- `/server.json`에서 future MCP registry/package manifest 초안 노출. (완료)
- `/healthz` 헬스체크 추가. (완료)
- Remote MCP registry에서는 `estimate_workspace_dxf` 숨김. 직접 호출해도 `WORKSPACE_PATHS_DISABLED` 반환. (완료)
- public bind host에서는 `FATTERN_REMOTE_MCP_TOKEN` 또는 `--bearer-token` 없으면 실행 차단. (완료)
- `docs/hosting.md`, README, AI client guide, developer guide 업데이트. (완료)
- 검수 후 정리: `/mcp`와 `/server.json`은 host 전용, `/hosting/policy`와 `/healthz`는 일반 Web UI에서도 열리는 진단 endpoint로 문서 분리 완료. (완료)
- 검수 후 정리: workspace `config/answers.json`이 있어도 명시 CLI flag가 우선하도록 보정 완료. (완료)

### v0.9.0 병렬 작업

| ID | 파트 | 담당 역할 | 작업 | 병렬 가능 여부 | 의존성 | 완료 기준 |
|---|---|---|---|---|---|---|
| D1 | Remote MCP Transport | MCP/backend engineer | `/mcp` POST JSON-RPC, GET 405, tool list/call 연결 | D2, D3와 병렬 가능 | 기존 stdio dispatcher | HTTP test에서 initialize/tools/list/tools/call 통과 |
| D2 | Hosted Web UI Boundary | Backend engineer | `fattern host`, `/healthz`, `/hosting/policy`, `/server.json` | D1과 병렬 가능 | Web UI server 구조 | local hosted-prep 서버가 같은 output/run 계약 사용 |
| D3 | Security Policy | Security engineer | public bind token 요구, Origin 검증, remote workspace path tool 비활성화 | D1과 병렬 가능 | remote MCP route | unsafe path tool 호출 차단 테스트 통과 |
| D4 | Docs | Technical writer | README, docs/hosting.md, AI client guide, developer guide 업데이트 | D1-D3와 병렬 가능 | endpoint 이름 확정 | 일반 사용자와 AI 사용자 route 구분 명확 |
| D5 | QA | QA engineer | HTTP MCP, CLI, Web UI, MCP 회귀 테스트 | D1-D4 후 집중 | 구현 완료 | unittest 전체 통과, diff check 통과 |

### v0.9.0 보류 조건과 남은 작업

- OAuth 2.1 protected-resource metadata와 token audience validation은 아직 미구현이다.
- 사용자 계정, 프로젝트 격리, 파일 retention job은 아직 미구현이다.
- 사용량 제한, 과금, enterprise BYOK는 아직 설계 단계다.
- public connector directory 제출은 아직 하지 않는다.

## Nesting 로드맵

v0.5와 v0.6에서는 큰 nesting 알고리즘 교체보다 도메인 모델 정리를 우선한다.

### 현재 기준

- bottom-left fill + beam search를 유지한다. (완료)
- bbox shelf fallback을 유지한다. (완료)
- polygon-aware 충돌 검증과 local compaction을 유지한다. (완료)

### v0.5-v0.7 단기 개선

- `allowed_rotation=[0, 180]`이면 piece별 두 방향을 시도하되 nap policy를 우선한다. (완료)
- shelf height 최적화는 작은 개선으로만 다룬다. (완료: `compact_within_shelf` 보조 step)
- initial sort에 longest-edge-down 후보를 추가 검토한다. (완료: longest-edge order와 rotation attempt 추가)
- no-overlap validation 캐싱을 검토한다. (완료: absolute outline/collision geometry cache 추가)

### Nesting 보류 항목 구현 힌트

각 보류 항목의 구현 진입점과 회귀 위험을 미리 적어둔다. 큰 nesting 교체는 v0.8 범위가 아니다. v0.8은 견적용 의사결정 레이어에 집중하고, 아래는 기존 BLF + beam search 골격을 유지한 채 끼워 넣을 수 있는 작업 위주다.

shelf height 최적화:

- 현재 BLF는 shelf의 첫 piece height로 shelf 천장이 고정되므로, 키 큰 piece 한 개가 shelf 윗공간을 낭비한다.
- 작은 개선안: nesting 직후 `compact_within_shelf()` 보조 step을 추가해 piece별로 shelf 천장 방향으로 끌어붙인다. 충돌 검증은 기존 polygon-aware 경로를 재사용하면 충분하고, BLF 결과는 깨지 않는다.
- 큰 개선안(v1.0 이후 후보): shelf 대신 x-축 height map(skyline) 모델로 교체하면 piece가 정확한 빈 슬롯에 들어간다. 골격 교체이므로 v0.8 견적 레이어 범위에는 넣지 않는다.
- 측정 지표: `metrics`에 `shelf_utilization = sum(piece_area_in_shelf) / (shelf_width * shelf_height)`를 추가하면 PR 단위 회귀 비교가 쉬워진다. happy-path 테스트의 numeric snapshot과 함께 묶으면 안전.

initial sort longest-edge-down:

- piece 회전이 허용되면 piece별로 "가장 긴 변이 marker 진행 방향에 평행"이 되도록 사전 회전한 뒤 정렬한다.
- 단, `nap_direction=one_way` 또는 piece-level grainline이 있으면 회전 자유도가 제한된다. 사전 회전은 항상 `allowed_rotation` 및 grainline/nap policy를 통과한 후보 안에서만 시도한다. policy 위반은 silent하게 떨어뜨리지 말고 warning 후보로 남긴다.
- 정렬 키 후보: `max(bbox_w, bbox_h)` 내림차순 → 동률 시 `area` 내림차순 → 동률 시 piece_id 사전순(결정성 확보).
- beam search와 자연 결합: 기존 정렬 후보 + longest-edge 후보를 두 attempt로 돌려 marker length가 짧은 쪽을 채택한다. 비용이 약 2배이므로 piece 수가 큰 입력에서는 `--no-extra-sort` 같은 끄는 스위치를 함께 둔다.
- 회귀 위험: shrinkage 적용 후 outline 기준으로 longest edge가 바뀐다. 사전 회전 결정은 shrinkage 단계 이후에 한다.

no-overlap validation 캐싱:

- 현재 polygon-aware SAT 충돌 검사가 dominant cost다. piece + rotation 단위 axis projection을 캐싱하면 반복 후보 좌표 평가에서 같은 piece의 재계산을 피한다.
- 캐시 키: `(piece_id, rotation_deg, shrinkage_scale_hash)`. shrinkage 적용 후 outline이 변하므로 캐시는 shrinkage 단계 직후에 빌드한다. canonical key를 만들 때 `(length_percent, width_percent)`를 그대로 넣지 말고 round 처리(예: 4자리)로 노이즈 차단.
- spatial index 보조: piece bbox 기준 grid cell에 placement를 등록하면 충돌 후보를 인접 cell로 제한해 O(n) → O(adjacent)로 줄어든다. grid 크기는 가장 큰 piece bbox의 절반 정도가 균형점.
- 캐시 효과 검증: `metrics`에 collision check 호출 횟수와 캐시 hit ratio를 임시로 노출하면 튜닝이 쉽다. 정식 metric으로 굳히지 말고 dev flag 뒤에 두는 게 안전.
- v1.0 이후 NFP 도입의 사전 단계로도 유용하다. NFP가 들어오면 axis projection 캐시는 piece pair NFP table로 자연스럽게 진화하므로, 캐싱 작업은 NFP 진입 비용을 낮추는 투자다.

현재 반영:

- bbox shelf fallback 결과에 `compact_within_shelf()`를 적용해 기존 polygon-aware refinement 경로로 빈 공간을 재사용한다.
- `_metric_orders`에 longest-edge sort key를 추가하고, 회전 후보가 2개 이상이면 longest-edge-down rotation attempt를 한 번 더 실행한다.
- `_CollisionGeometryCache`로 validation과 candidate 충돌 검사에서 absolute outline/collision points, bounds, edge bounds를 재사용한다.
- 복잡한 outline 입력에서는 추가 rotation attempt를 비활성화해 비용 증가를 제한한다.

### v1.0 이후

- No-Fit Polygon 기반 후보 좌표 생성을 검토한다.
- piece order와 rotation 최적화에는 Simulated Annealing 또는 Genetic Algorithm을 검토한다.
- NFP와 SA/GA는 v0.5-v0.6 범위에 넣지 않는다.

## 남은 어려운 문제

현재 v0.5-v0.7 구현은 제품 계약과 deterministic guardrail을 닫은 MVP다. 아래 항목은 아직 상용 marker CAD 수준으로 해결된 것이 아니다.

- AAMA/ASTM 실제 layer 매핑은 근거 부족 상태다. 현재 numeric layer는 low-confidence candidate와 warning으로만 처리하고, `layer_audit`로 판단 근거를 노출한다.
- grainline 자동 감지는 단순 layer rule과 line midpoint 포함 판정 기반이다. 오탐 가능성이 크므로 confidence와 warning을 유지해야 한다.
- piece name/size는 `piece=...;size=...` 같은 explicit metadata만 읽는다. 일반 layer명이나 text annotation에서 의미를 추론하지 않는다.
- shrinkage는 grainline 축 기준 단순 affine scale이다. warp/weft, 소재별 비선형 수축, piece별 예외는 아직 다루지 않는다.
- PDF는 report text를 감싼 단일 페이지 PDF다. 고급 레이아웃, 표/도면 정렬, multi-page plotter PDF는 별도 범위다.
- marker CAD급 nesting은 아직 아니다. stripe/plaid matching, fold piece, mirrored pair, bundle/section 배치, piece pairing은 v1.0 이후 범위다.
- AAMA/ASTM 호환성은 실제 샘플 다양성이 없으면 검증 불충분이다. 샘플 fixture와 vendor별 import/export round-trip 검증이 필요하다.

## 우선순위

완료된 우선순위:

1. 고수준 `calculate_marker_yield` tool (완료)
2. CLI를 `calculate_marker_yield` 입력 shape로 통합하고 `answers.json` canonical schema 작성 (완료)
3. `nap_direction=one_way`에서 grainline 정책 enforcement 보완 (완료)
4. schema 정교화 (완료: v0.7.0-v0.8.4 범위의 schema/test 동기화 완료. 새 조건 추가 시 재동기화 필수)
5. `cuttable_width`, `size_ratio`, `piece_quantity`, `spacing`, `nap_direction` (완료)
6. 식서 blocker 정책 강화 (완료: 단, 자동 감지는 low-confidence guardrail 유지)
7. CSV 출력 (완료: placement-level + explicit piece metadata + piece-level grainline status)
8. AAMA/ASTM 의미 인식 (부분 완료: low-confidence numeric layer candidate, 근거 불충분 warning, layer audit 제공)
9. PDF 출력 (완료: 단일 페이지 report PDF)
10. 견적용 `minimum_yield`/`quote_yield` 분리 (완료)
11. 로컬 Web UI 1차 추가 (완료)
12. `fattern` 기본 실행 Web UI 자동 오픈 (완료)
13. `input/`, `output/`, `config/` 폴더 자동 생성 (완료)
14. Web UI 첫 화면 안내문과 질문지 자동 표시 (완료)
15. Web UI/CLI/MCP 결과를 `output/run_id/`에 정리 저장 (완료)
16. MCP high-level 결과에 `web_url`, `preview_url`, `output_dir` 포함 (완료)
17. workspace-relative DXF path tool 추가 (완료)
18. README 첫 화면 일반 사용자용 한 줄 설치/실행 중심 정리 (완료)
19. LLM 없는 deterministic Advisor 패널 추가 (완료)
20. API key가 있는 환경에서만 선택형 LLM Advisor 추가 (완료)
21. repository hygiene와 계약 검수 (완료)

다음 우선순위:

1. hosted Web UI와 remote MCP는 로컬 투트랙 안정화 이후 검토한다.
2. LLM Advisor streaming, rate limit, audit log masking을 제품 운영 요구에 맞게 확장한다.
3. buyer/vendor별 allowance preset과 costing은 v0.9 이후로 다룬다.

## 주요 리스크

- AAMA/ASTM DXF는 실제 샘플 다양성이 필요하다.
- grainline 자동 감지는 오탐 가능성이 크다.
- seam allowance 자동 인식은 아직 하지 않는다. 현재는 `included`/`excluded`와 fallback rough 확장만 완료 상태다.
- nesting 고도화는 시간이 많이 든다.
- 사용자가 결과를 생산용 확정 요척으로 오해하면 제품 리스크가 크다.
- Web UI에 LLM을 직접 붙일 경우 API 비용, key 보안, 원본 DXF 유출 리스크가 있다. LLM Advisor는 선택형으로 두고 서버 환경변수 기반 key 관리가 필요하다.
- MCP workspace-relative path tool은 접근성을 올리지만 local file read 공격면을 넓힐 수 있다. absolute path, `..`, 비 DXF 확장자, workspace 밖 접근은 차단해야 한다.
- Web UI와 MCP가 서로 다른 artifact 저장 경로를 쓰면 사용자와 AI가 다른 결과를 보게 된다. run registry와 output 계약을 하나로 고정해야 한다.
- piece pairing, fold piece, stripe/plaid matching, bundle/section 배치는 v1.0 이후 별도 범위다.
- plotter용 multi-page PDF는 PDF report 이후 별도 범위다.

## 제품 경고 문구 방향

Fattern 결과는 DXF 기반 rough marker yield 추정이다. 생산용 확정 요척, 발주 확정값, 상용 marker CAD 대체 결과로 표시하면 안 된다.

report에는 아래 의미가 드러나야 한다.

- 입력 DXF와 조건 기준의 추정 결과
- grainline, seam allowance, nap direction 조건의 검증 상태
- blocker와 warning
- 계산에 사용된 fabric width 또는 cuttable width
- 회전 허용값
- 단위 기준

## 실행 결론

v0.9.0 기준으로 **일반 사용자용 Web UI + AI 사용자용 MCP 투트랙 + 같은 output/run 계약 + 선택형 Advisor + hosted-prep Remote MCP HTTP 경계**까지 진행한다. production hosted service는 OAuth, retention, quota, tenant isolation 이후로 둔다.

현재 제품 계약은 Web UI, Codex, Claude Code, CLI, MCP 모두에서 아래 흐름으로 고정한다.

```text
Web UI 업로드 또는 MCP workspace path 또는 질문지 답변 + DXF
  -> calculate_marker_yield
  -> deterministic engine
  -> minimum_yield
  -> quote layer allowance_policy
  -> quote_yield + confidence
  -> output/run_id
  -> JSON/SVG/CSV/Markdown/PDF/run_summary output
  -> Web UI result URL
  -> optional export_artifacts zip
```

MCP에서는 자동 팝업 질문지를 강제하지 않는다. 서버는 `prompts/list`/`prompts/get`으로 `/fattern`, `/fattern-help`, `/fattern-estimate`에 해당하는 start guide를 제공하고, host AI가 그 안내에 따라 누락값만 묻는다. Web UI는 반대로 첫 화면에 질문지를 자동 표시한다.
