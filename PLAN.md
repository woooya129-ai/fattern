# Fattern PLAN

## 제품 방향

Fattern은 `LLM 가요척 계산기`가 아니다.

Fattern의 제품 정의는 **DXF 기반 deterministic marker yield engine + LLM 오케스트레이터**다.

LLM은 계산 주체가 아니라 작업 지시자다. 사용자 입력을 정리하고, 필요한 질문을 만들고, MCP tool 호출 순서를 제어하고, blocker를 판단하고, tool output을 사람이 읽기 쉬운 결과로 설명한다.

Engine은 계산 주체다. DXF/AAMA/ASTM 파싱, polygon 추출, grainline, seam allowance, 수량 조건 처리, nesting, marker length, utilization, waste 계산, SVG/CSV/PDF 출력을 담당한다.

## 현재 완료 상태

- 릴리스 표기: `pyproject.toml`, `README.md`, `README.en.md` 기준 `0.7.0`으로 정리 완료.
- 빠른 이해와 설치 문서: README 양쪽에 빠른 이해, 설치 방법, 실행 예시, 산출물 목록 반영 완료.
- 고수준 경로: `calculate_marker_yield`, CLI `estimate`, canonical `answers.json` 연동 완료.
- 조건 엔진: `cuttable_width`, `size_ratio`, `piece_quantity`, `spacing`, `nap_direction`, `fabric_type`, `shrinkage`, `stretch_direction`, `seam_allowance` 정책 반영 완료.
- blocker 정책: cuttable width 초과, one-way 180 회전, woven/grainline required/one-way grainline missing, invalid nap, invalid shrinkage, invalid seam fallback 차단 완료.
- DXF 의미 분리: `LINE`은 grainline 후보 또는 internal line으로 분리하고, `TEXT`/`MTEXT`는 annotation으로 제외 완료.
- DXF layer audit: `parse_dxf`와 `extract_pattern_pieces` 응답에 layer별 entity count, grainline candidate source, confidence, mapping status 노출 완료.
- Nesting 개선: shelf compact 보조 step, longest-edge-down attempt, overlap geometry cache 반영 완료.
- 리포트 산출물: `result.json`, `marker_preview.svg`, `marker_report.md`, `marker_report.pdf`, `report.csv`, 별도 zip export 경로 완료.
- 계약 정리: LLM-facing schema, MCP tool schema, README 예시, 테스트 계약 동기화 완료.
- 검수 기준: `python -m unittest discover -s tests` 기준 162 tests OK, 1 skipped.

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

`calculate_marker_yield`는 `export_artifact_ids` 리스트만 반환한다. 실제 zip은 클라이언트가 `export_artifacts`를 별도 호출해서 생성한다. 이 별도 호출 방식이 v0.7.0 현재 확정 정책이며 완료 상태다.

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

각 보류 항목의 구현 진입점과 회귀 위험을 미리 적어둔다. 큰 nesting 교체는 v0.8 범위이므로 아래는 모두 기존 BLF + beam search 골격을 유지한 채 끼워 넣을 수 있는 작업 위주다.

shelf height 최적화:

- 현재 BLF는 shelf의 첫 piece height로 shelf 천장이 고정되므로, 키 큰 piece 한 개가 shelf 윗공간을 낭비한다.
- 작은 개선안: nesting 직후 `compact_within_shelf()` 보조 step을 추가해 piece별로 shelf 천장 방향으로 끌어붙인다. 충돌 검증은 기존 polygon-aware 경로를 재사용하면 충분하고, BLF 결과는 깨지 않는다.
- 큰 개선안(v0.8 후보): shelf 대신 x-축 height map(skyline) 모델로 교체하면 piece가 정확한 빈 슬롯에 들어간다. 골격 교체이므로 v0.7 안에는 넣지 않는다.
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
- v0.8 NFP 도입의 사전 단계로도 유용하다. NFP가 들어오면 axis projection 캐시는 piece pair NFP table로 자연스럽게 진화하므로, 캐싱 작업은 NFP 진입 비용을 낮추는 투자다.

현재 반영:

- bbox shelf fallback 결과에 `compact_within_shelf()`를 적용해 기존 polygon-aware refinement 경로로 빈 공간을 재사용한다.
- `_metric_orders`에 longest-edge sort key를 추가하고, 회전 후보가 2개 이상이면 longest-edge-down rotation attempt를 한 번 더 실행한다.
- `_CollisionGeometryCache`로 validation과 candidate 충돌 검사에서 absolute outline/collision points, bounds, edge bounds를 재사용한다.
- 복잡한 outline 입력에서는 추가 rotation attempt를 비활성화해 비용 증가를 제한한다.

### v0.8 이후

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

1. 고수준 `calculate_marker_yield` tool (완료)
2. CLI를 `calculate_marker_yield` 입력 shape로 통합하고 `answers.json` canonical schema 작성 (완료)
3. `nap_direction=one_way`에서 grainline 정책 enforcement 보완 (완료)
4. schema 정교화 (완료: v0.7.0 범위의 schema/test 동기화 완료. 새 조건 추가 시 재동기화 필수)
5. `cuttable_width`, `size_ratio`, `piece_quantity`, `spacing`, `nap_direction` (완료)
6. 식서 blocker 정책 강화 (완료: 단, 자동 감지는 low-confidence guardrail 유지)
7. CSV 출력 (완료: placement-level + explicit piece metadata + piece-level grainline status)
8. AAMA/ASTM 의미 인식 (부분 완료: low-confidence numeric layer candidate, 근거 불충분 warning, layer audit 제공)
9. PDF 출력 (완료: 단일 페이지 report PDF)
10. README 빠른 이해와 설치 방법 정리 (완료)
11. repository hygiene와 계약 검수 (완료)

## 주요 리스크

- AAMA/ASTM DXF는 실제 샘플 다양성이 필요하다.
- grainline 자동 감지는 오탐 가능성이 크다.
- seam allowance 자동 인식은 아직 하지 않는다. 현재는 `included`/`excluded`와 fallback rough 확장만 완료 상태다.
- nesting 고도화는 시간이 많이 든다.
- 사용자가 결과를 생산용 확정 요척으로 오해하면 제품 리스크가 크다.
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

v0.7.0까지는 nesting 알고리즘만 더 파는 것보다 **고수준 tool + schema + 조건 엔진 + 리포트 계약**을 먼저 닫는 방향으로 정리했고, 이 범위는 완료 상태다.

현재 제품 계약은 Codex, Claude Code, CLI, MCP 모두에서 아래 흐름으로 고정한다.

```text
질문지 답변 + DXF
  -> calculate_marker_yield
  -> deterministic engine
  -> JSON/SVG/CSV/Markdown/PDF output
  -> optional export_artifacts zip
```
