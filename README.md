# Fattern

[English](README.en.md)

DXF 의류 패턴으로 가요척을 빠르게 추정하는 CLI/MCP 도구.

Fattern은 **FAST + PATTERN = FATTERN**이라는 뜻이다.

이 저장소는 **source-available, noncommercial use only**다. 라이선스는 **PolyForm Noncommercial License 1.0.0 + 별도 Commercial License** 구조다.

## 한 줄 사용

DXF를 `input/` 폴더에 넣고 `input/answers.json`을 만든 뒤 실행한다.

```powershell
python -m fattern estimate
```

바로 옵션으로 실행할 수도 있다.

```powershell
python -m fattern estimate input\sample.dxf --fabric-width 150 --unit cm --dxf-unit auto --grainline-status unknown --seam-allowance-included no --one-way-fabric no --rotation 0
```

결과는 항상 `output/YYYYMMDD-HHMMSS_DXF이름/` 아래에 정리된다.

```text
output/
  20260517-223500_Simple-T/
    marker_preview.svg
    marker_report.md
    result.json
```

## 제일 쉬운 흐름

1. `input/` 폴더를 만든다.
2. DXF 파일을 하나 넣는다.
3. 질문지를 확인한다.

```powershell
python -m fattern questionnaire
```

4. `input/answers.json`을 만든다.

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

5. 실행한다.

```powershell
python -m fattern estimate
```

`input/` 방식은 비전공자에게 제일 쉽다. 자동화 스크립트에서는 DXF 경로를 직접 넘기는 방식이 더 명확하다. MCP에서는 보안 때문에 경로를 넘기지 않고 `register_input_file`로 파일명과 base64 내용을 등록한다.

## Codex, Claude Code에서 한 줄

Codex:

```text
input 폴더의 DXF와 answers.json으로 python -m fattern estimate 실행하고 output 결과를 요약해줘.
```

Claude Code:

```text
Run python -m fattern estimate using the DXF and answers.json in input/, then summarize the files created under output/.
```

## 질문지 항목

`python -m fattern questionnaire`는 아래 항목을 묻는다.

- `dxf_file`: DXF 파일 또는 MCP file_id
- `fabric_width`: 원단 폭
- `unit`: 결과 단위, `mm`, `cm`, `m`, `inch`, `ft`, `yd`
- `dxf_unit_hint`: DXF 좌표 단위, 보통 `auto`
- `grainline_status`: 식서선 확인 여부, `present`, `missing`, `unknown`
- `seam_allowance_included`: 시접 포함 여부
- `seam_allowance_width`: 시접 미포함일 때 평균 시접값
- `one_way_fabric`: 원웨이 원단 여부
- `rotation_allowed_degrees`: 허용 회전, 기본 `[0]`
- `clearance`: 피스 사이 간격

## 원단 폭 기준

전세계 실무에서 자주 보이는 폭을 질문지 프리셋으로 제공한다. 표준은 하나로 고정되어 있지 않으니 실제 원단 폭을 알면 직접 입력하는 게 맞다.

- `44-45 in / 112-115 cm`: 기본 의류, 퀼팅 코튼, 소품
- `54 in / 137 cm`: 의류, 홈데코, 일부 실내장식 원단
- `58-60 in / 147-152 cm`: 니트, 원피스, 코트 등 대폭 의류 원단
- `108 in / 274 cm`: 침구, 퀼트 backing, 대형 패널
- `118 in / 300 cm`: 커튼, 쉬어 커튼 같은 초광폭 원단
- `custom`: 실제 원단 폭 직접 입력

## 식서와 회전 규칙

식서는 의류 요척에서 민감한 조건이다. Fattern의 기본 회전은 `0`도만 허용한다.

패턴을 돌리고 싶으면 사용자가 명시적으로 `--rotation 0,180` 또는 `--rotation 0,90,180,270`을 넣어야 한다. 식서선이 없거나 확인되지 않았는데 회전을 허용하면 결과에는 경고가 붙는다.

원웨이 원단에서 식서선이 `missing`이면 배치를 중단한다. 이 경우 DXF 식서 레이어를 정리하거나 `grainline_status`를 확인해야 한다.

자세한 배치 기준은 [docs/marker-rules.md](docs/marker-rules.md)를 봐라.

## 시접 기본값

패턴에 시접이 없으면 `seam_allowance_included`를 `no`로 둔다. 그러면 평균 시접값을 rough 계산에 넣는다.

- `mm`: `10.0`
- `cm`: `1.0`
- `m`: `0.01`
- `inch`: `0.375`
- `ft`: `0.03125`
- `yd`: `0.0104167`

이 값은 CAD offset curve가 아니라 평균 확장 추정이다. 생산용 확정 요척으로 보면 안 된다.

## DXF 단위 자동 추정

기본값은 `--dxf-unit auto`다. 의류 패턴 크기와 원단 폭을 기준으로 `mm`, `cm`, `m`, `inch`, `ft`, `yd` 후보를 비교한다.

DXF가 애매하면 직접 지정해라.

```powershell
python -m fattern estimate input\sample.dxf --fabric-width 150 --unit cm --dxf-unit mm --grainline-status unknown --seam-allowance-included yes --one-way-fabric no
```

## SVG 출력

`marker_preview.svg`에는 실제 원단 경계, 배치된 패턴 outline, 원단 폭, marker length, 식서 상태, 허용 회전이 표시된다. 식서 방향 표시도 빈 공간 정보 패널에 함께 나온다.

## MCP

stdio 서버:

```powershell
python -m fattern mcp-stdio
```

설정 예:

```json
{
  "command": "python",
  "args": ["-m", "fattern", "mcp-stdio"],
  "cwd": "C:\\obs\\fattern"
}
```

MCP 클라이언트가 prompts를 slash UI로 노출하면 `/fattern-help`, `/fattern-estimate` 같은 도움말을 볼 수 있다. 이건 클라이언트 지원 여부에 달려 있다. 서버 쪽에서는 `prompts/list`, `prompts/get`을 지원한다.

MCP tool input에는 DXF 경로를 넣지 않는다. 순서는 아래처럼 간다.

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

중간에 `severity=blocker` 에러가 나오면 다음 계산 tool을 호출하지 않는다.

## 지원 범위

- closed LWPOLYLINE
- R12 `POLYLINE + VERTEX + SEQEND`
- bbox baseline + polygon-aware compact rough marker
- 피스 outline 기반 SVG 렌더링
- 평균 시접 rough 확장
- DXF autoscale
- MCP stdio transport

아직 지원하지 않는 것:

- 임의 각도 회전
- 모든 DXF entity와 모든 CAD layer convention 자동 해석
- 곡선 고정밀 flattening
- 프린트 매칭
- 상용 CAD 수준의 최종 nesting

## 개발

```powershell
python -m unittest discover -s tests
```

## 라이선스

이 프로젝트는 **PolyForm Noncommercial License 1.0.0** 기반 source-available 소프트웨어다.

비상업 목적에서는 라이선스 조건에 따라 사용, 학습, 수정, 공유할 수 있다.

상업 사용, 운영 환경 사용, 유료 컨설팅, 재판매, 호스팅 서비스, 상업 워크플로 통합은 저작권자의 별도 서면 상업 라이선스가 필요하다.

- [LICENSE](LICENSE)
- [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)
- [NOTICE](NOTICE)

상업 사용을 제한하므로 OSI 승인 오픈소스는 아니다.
