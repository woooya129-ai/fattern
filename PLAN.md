# Fattern PLAN

## 제품 방향

Fattern은 `LLM 가요척 계산기`가 아니다.

Fattern의 제품 정의는 **DXF 기반 deterministic marker yield engine + LLM 오케스트레이터**다.

LLM은 계산 주체가 아니라 작업 지시자다. 사용자 입력을 정리하고, 필요한 질문을 만들고, MCP tool 호출 순서를 제어하고, blocker를 판단하고, tool output을 사람이 읽기 쉬운 결과로 설명한다.

Engine은 계산 주체다. DXF/AAMA/ASTM 파싱, polygon 추출, grainline, seam allowance, 수량 조건 처리, nesting, marker length, utilization, waste 계산, SVG/CSV/PDF 출력을 담당한다.

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
- `size_ratio`는 v0.4 schema 확정 전 의미를 잠근다. v0.7 현재는 base size 복제 모델로 반영하고 `SIZE_RATIO_BASE_SIZE_REPLICATED` warning을 남긴다.
- `cuttable_width > fabric_width`, grainline/nap 직교 정책, shrinkage 적용 가능 조건을 schema와 engine policy에 반영한다. (완료)
- 기존 tool chain을 감싸는 orchestration wrapper 구현 (완료: `McpToolRegistry._calculate_marker_yield`)
- blocker 발생 시 partial result와 중단 이유 반환 (완료)
- `export_artifacts`에 `result.json`, `marker_preview.svg`, `marker_report.md`, `marker_report.pdf`, `report.csv` 포함 (artifact ID는 반환되지만 자동 zip export는 아님. 클라이언트가 `export_artifacts`를 별도 호출해야 한다.)
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

`calculate_marker_yield`는 `export_artifact_ids` 리스트만 반환한다. 실제 zip은 클라이언트가 `export_artifacts`를 별도 호출해서 생성한다. 자동 zip은 현재 v0.4 범위 밖이다. 자동 export를 v0.4 DoD에 포함할지 v0.5 이후로 미룰지는 별도 결정 항목이다.

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
- `fabric_type=knit`이면 `stretch_direction` 필드 추가를 검토한다.
- shrinkage는 길이 방향과 폭 방향을 나눌 수 있게 설계한다.
- `spacing`은 piece 간 최소 간격으로 해석한다.
- `size_ratio`는 graded DXF 모델과 base size 복제 모델 중 하나를 선택한 뒤 반영한다.
- `piece_quantity`는 DXF 또는 사용자 입력에서 온 수량 조건으로 분리한다.
- `grainline_required`는 `nap_direction`과 독립된 조건이다.
- woven 원단에서 grainline이 missing이면 nap direction과 무관하게 blocker다.
- `nap_direction`은 회전 허용값에만 영향을 준다. `one_way`에서는 180 회전을 차단한다.
- `cuttable_width > fabric_width`는 blocker다.

현재 구현 상태:

- `piece_quantity`는 piece id 또는 `*` 키 기준으로 base outline을 복제한다.
- `size_ratio`와 `piece_quantity`가 함께 있으면 두 수량 조건을 곱해 복제한다.
- `shrinkage_percent`와 `shrinkage.length_percent/width_percent`를 지원한다.
- piece-level grainline이 있으면 grainline 축/직교 축 기준으로 shrinkage를 적용한다.
- piece-level grainline이 없으면 shrinkage를 적용하지 않고 warning을 반환한다.
- `fabric_type=knit`은 `stretch_direction` 입력을 받는다. 현재 marker engine은 stretch matching을 적용하지 않고 warning으로 노출한다.

### v0.5.0 설계 메모

`size_ratio`는 아래 둘 중 하나로 확정해야 한다.

```text
graded DXF 필수:
  AAMA/ASTM piece set 안에 사이즈별 outline이 있을 때만 size_ratio를 허용한다.
  piece name과 size suffix는 engine이 deterministic하게 매칭한다.

base size 복제:
  단일 base size outline을 수량만큼 복제한다.
  grading은 무시되며 report에 경고를 표시한다.
```

현재 구현은 base size 복제 모델을 선택한다.

- 단일 base outline을 `size_ratio` 수량만큼 복제한다.
- grading 차이는 추론하지 않는다.
- grading 무시는 `SIZE_RATIO_BASE_SIZE_REPLICATED` warning으로 표시한다.
- CSV에는 복제된 placement별 `size`와 `quantity=1`을 채운다.
- graded DXF size suffix 매칭은 explicit layer metadata(`piece=...;size=...`)가 있을 때만 사용한다. 일반 layer name에서 의미를 추론하지 않는다.

`shrinkage_percent`는 단일 숫자 입력을 허용하되 내부 모델은 아래 구조로 확장한다.

```json
{
  "length_percent": 3,
  "width_percent": 0
}
```

shrinkage 적용 정책은 아래와 같다.

- shrinkage는 piece의 grainline 축 기준 비등방 스케일링이다.
- nesting과 metrics 계산 이전에 outline에 적용한다.
- 길이 방향은 grainline 축, 폭 방향은 grainline에 직교한 축이다.
- piece별 grainline이 없으면 shrinkage를 적용하지 않고 warning 또는 blocker를 반환한다.
- `percent >= 100`이면 scale이 무한대가 되므로 blocker다.

`seam_allowance.status`는 최소 아래 상태를 구분한다.

```text
included
excluded
unknown
```

`unknown` 상태에서 fallback을 적용할지 blocker로 볼지는 fabric type과 제품 정책에 따라 분리한다.

v0.5 시접 범위는 아래로 한정한다.

- piece 단위 uniform fallback width까지만 자동 적용한다.
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

- DXF `LINE` entity를 geometry 계산에서 분리하고 grainline 후보 또는 internal line으로만 다룬다.
- 명시 `grainline_layer_names`는 confidence 1.0 grainline rule이다.
- `GRAINLINE`, `GRAIN_LINE`, `GRAIN-LINE` 등 deterministic layer name은 confidence 0.8 후보로 둔다.
- numeric layer `7`은 AAMA/ASTM 후보로만 다루며 `AAMA_ASTM_LAYER_MAPPING_UNVERIFIED` warning을 반환한다. 로컬 근거가 충분하지 않아서 high-confidence hardcode가 아니다.
- piece name/size는 explicit layer metadata 형식 `piece=Front;size=M`만 읽는다.
- `TEXT`/`MTEXT`는 untrusted annotation으로 분리하고 geometry 계산에서 제외한다.
- grainline 후보가 아닌 `LINE`은 internal line으로 제외하고 warning을 반환한다.

## v0.7.0 목표: 리포트 제품화

v0.7.0은 계산 결과를 사용자와 다른 도구가 안정적으로 소비할 수 있게 만드는 단계다.

출력 우선순위는 아래와 같다.

1. SVG preview
2. JSON result
3. CSV report
4. Markdown report
5. PDF report

PDF report는 단일 페이지 텍스트 PDF artifact로 생성한다. JSON, CSV, Markdown이 주 계약이고 PDF는 동일 report text를 휴대용 산출물로 감싼다.

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

- 숫자는 tool output만 사용한다.
- report와 `result.json`의 숫자는 일치해야 한다.
- warning은 누락 없이 표시한다.
- blocker가 있으면 결과 대신 중단 사유와 partial artifact 상태를 표시한다.
- 사용자 입력, DXF layer명, piece명은 escape한다.
- SVG에는 `script`, `foreignObject`, external href, remote resource를 넣지 않는다.

## Nesting 로드맵

v0.5와 v0.6에서는 큰 nesting 알고리즘 교체보다 도메인 모델 정리를 우선한다.

### 현재 기준

- bottom-left fill + beam search를 유지한다.
- bbox shelf fallback을 유지한다.
- polygon-aware 충돌 검증과 local compaction을 유지한다.

### v0.5-v0.7 단기 개선

- `allowed_rotation=[0, 180]`이면 piece별 두 방향을 시도하되 nap policy를 우선한다.
- shelf height 최적화는 작은 개선으로만 다룬다.
- initial sort에 longest-edge-down 후보를 추가 검토한다.
- no-overlap validation 캐싱을 검토한다.

### v0.8 이후

- No-Fit Polygon 기반 후보 좌표 생성을 검토한다.
- piece order와 rotation 최적화에는 Simulated Annealing 또는 Genetic Algorithm을 검토한다.
- NFP와 SA/GA는 v0.5-v0.6 범위에 넣지 않는다.

## 남은 어려운 문제

현재 v0.5-v0.7 구현은 제품 계약과 deterministic guardrail을 닫은 MVP다. 아래 항목은 아직 상용 marker CAD 수준으로 해결된 것이 아니다.

- AAMA/ASTM 실제 layer 매핑은 근거 부족 상태다. 현재 numeric layer는 low-confidence candidate와 warning으로만 처리한다.
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
4. schema 정교화 (진행 중: 새 조건 추가 시 schema/test 동기화 필수)
5. `cuttable_width`, `size_ratio`, `piece_quantity`, `spacing`, `nap_direction` (완료)
6. 식서 blocker 정책 강화 (완료: 단, 자동 감지는 low-confidence guardrail 유지)
7. CSV 출력 (완료: placement-level + explicit piece metadata + piece-level grainline status)
8. AAMA/ASTM 의미 인식 (부분 완료: low-confidence numeric layer candidate만 제공, 근거 불충분 warning 유지)
9. PDF 출력 (완료: 단일 페이지 report PDF)

## 주요 리스크

- AAMA/ASTM DXF는 실제 샘플 다양성이 필요하다.
- grainline 자동 감지는 오탐 가능성이 크다.
- seam allowance 자동 인식은 단순하지 않다.
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

다음 개발은 nesting 알고리즘만 더 파는 것보다 **고수준 tool + schema + 조건 엔진**이 먼저다.

이 순서가 먼저 잡혀야 Codex, Claude Code, CLI, MCP 모두에서 아래 흐름이 안정적으로 굴러간다.

```text
질문지 답변 + DXF
  -> calculate_marker_yield
  -> deterministic engine
  -> JSON/SVG/CSV/Markdown output
```
