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
  "spacing": 5,
  "allowed_rotation": [0],
  "grainline_required": true,
  "nap_direction": "one_way",
  "shrinkage_percent": 3,
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

- `calculate_marker_yield` MCP schema 추가
- Python tool schema와 JSON schema 동기화
- CLI에서 같은 request 구조 사용
- `input/answers.json`을 `calculate_marker_yield` request와 최대한 유사하게 정리
- 기존 tool chain을 감싸는 orchestration wrapper 구현
- blocker 발생 시 partial result와 중단 이유 반환
- `export_artifacts`에 `result.json`, `marker_preview.svg`, `marker_report.md`, `report.csv` 포함

### v0.4.0 DoD

- `calculate_marker_yield` schema가 추가되어 있다.
- CLI와 MCP가 같은 request 구조를 사용한다.
- `input/answers.json` 구조가 고수준 request와 크게 다르지 않다.
- output에 아래 파일이 생성된다.

```text
result.json
marker_preview.svg
marker_report.md
report.csv
```

- blocker 발생 시 중간 산출물과 이유가 명확히 표시된다.
- blocker 이후 다음 계산 tool이 호출되지 않는다.
- tool output 숫자와 report 숫자가 일치한다.
- path traversal 방어가 유지된다.
- warning이 report에 표시된다.

### v0.4.0 테스트

- happy path
- missing grainline
- invalid rotation
- `cuttable_width` 우선
- `size_ratio` 반영

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
- `size_ratio`는 marker 내 piece 복제 수량에 반영한다.
- `piece_quantity`는 DXF 또는 사용자 입력에서 온 수량 조건으로 분리한다.

### v0.5.0 설계 메모

`shrinkage_percent`는 단일 숫자 입력을 허용하되 내부 모델은 아래 구조로 확장 가능해야 한다.

```json
{
  "length_percent": 3,
  "width_percent": 0
}
```

`seam_allowance.status`는 최소 아래 상태를 구분한다.

```text
included
excluded
unknown
```

`unknown` 상태에서 fallback을 적용할지 blocker로 볼지는 fabric type과 제품 정책에 따라 분리한다.

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

## v0.7.0 목표: 리포트 제품화

v0.7.0은 계산 결과를 사용자와 다른 도구가 안정적으로 소비할 수 있게 만드는 단계다.

출력 우선순위는 아래와 같다.

1. SVG preview
2. JSON result
3. CSV report
4. Markdown report
5. PDF report

PDF report는 마지막에 둔다. 먼저 JSON, CSV, Markdown의 계약을 안정화한다.

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

### 리포트 원칙

- 숫자는 tool output만 사용한다.
- report와 `result.json`의 숫자는 일치해야 한다.
- warning은 누락 없이 표시한다.
- blocker가 있으면 결과 대신 중단 사유와 partial artifact 상태를 표시한다.
- 사용자 입력, DXF layer명, piece명은 escape한다.
- SVG에는 `script`, `foreignObject`, external href, remote resource를 넣지 않는다.

## 우선순위

1. 고수준 `calculate_marker_yield` tool
2. schema 정교화
3. `cuttable_width`, `size_ratio`, `spacing`, `nap_direction`
4. 식서 blocker 정책 강화
5. CSV 출력
6. AAMA/ASTM 의미 인식
7. PDF 출력

## 주요 리스크

- AAMA/ASTM DXF는 실제 샘플 다양성이 필요하다.
- grainline 자동 감지는 오탐 가능성이 크다.
- seam allowance 자동 인식은 단순하지 않다.
- nesting 고도화는 시간이 많이 든다.
- 사용자가 결과를 생산용 확정 요척으로 오해하면 제품 리스크가 크다.

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
