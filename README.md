# Fattern

[English](README.en.md)

DXF 의류 패턴으로 가요척을 빠르게 추정하는 CLI/MCP 도구.

Fattern은 **FAST + PATTERN = FATTERN**이라는 뜻이다.

현재 버전: **0.7.1**

이 저장소는 **source-available, noncommercial use only**다. 라이선스는 **PolyForm Noncommercial License 1.0.0 + 별도 Commercial License** 구조다.

## 빠른 이해

- Fattern은 LLM 계산기가 아니라 **DXF 기반 deterministic marker yield engine**이다.
- 입력은 DXF 패턴과 원단 조건이고, 출력은 rough marker 추정 결과다.
- 주요 산출물은 `result.json`, `marker_preview.svg`, `marker_report.md`, `marker_report.pdf`, `report.csv`다.
- v0.7.1 기준 CSV/PDF report, canonical `answers.json`, 고수준 MCP tool `calculate_marker_yield`, legacy DXF fallback을 지원한다.
- 생산용 확정 요척이나 상용 CAD nesting 대체품은 아니다.

## 설치 방법

Python **3.11 이상**이 필요하다.

```powershell
git clone <repo-url>
cd fattern
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

설치 확인:

```powershell
fattern --help
fattern questionnaire
```

설치하지 않고 소스 트리에서 바로 실행하려면:

```powershell
$env:PYTHONPATH = "src"
python -m fattern --help
```

## How to use

가장 쉬운 사용법은 `input/` 폴더 방식이다.

1. `input/` 폴더를 만든다.
2. DXF 파일을 하나 넣는다.
3. `input/answers.json`을 만든다.
4. `python -m fattern estimate`를 실행한다.
5. `output/` 아래 새로 생긴 폴더에서 결과를 확인한다.

처음 보면 아래 순서로 확인하면 된다.

1. `marker_report.md`: 사람이 읽는 요약. 원단 폭, marker length, 효율, warning을 먼저 본다.
2. `marker_preview.svg`: 배치 그림. 패턴이 원단 폭 밖으로 나갔는지, 회전이 의도와 맞는지 본다.
3. `report.csv`: 피스별 좌표와 회전값. 스프레드시트나 후속 자동화에 쓴다.
4. `result.json`: tool chain 결과. MCP, Codex, Claude Code 같은 자동화가 읽기 좋다.
5. `marker_report.pdf`: 공유용 단일 페이지 리포트.

DXF 레이어가 애매하면 MCP의 `parse_dxf` 또는 `extract_pattern_pieces` 결과에서 `layer_audit`을 확인한다. 레이어별 entity 수, grainline 후보 근거, confidence, mapping status가 나온다. 숫자 레이어 `7`은 AAMA/ASTM 후보로만 표시되며, 검증된 CAD vendor mapping으로 확정하지 않는다.

배치는 기존 BLF + beam search 골격을 유지한다. v0.7.1 기준 shelf compact 보조 step, longest-edge-down attempt, overlap geometry cache가 들어가서 작은 케이스의 빈 공간 재사용과 충돌 검사 반복 비용이 개선됐다. 그래도 상용 CAD급 최종 nesting은 아니다.

## 한 줄 사용

DXF를 `input/` 폴더에 넣고 `input/answers.json`을 만든 뒤 실행한다.

```powershell
python -m fattern estimate
```

바로 옵션으로 실행할 수도 있다.

```powershell
python -m fattern estimate input\sample.dxf --fabric-width 150 --unit cm --seam-allowance-status included --nap-direction two_way --grainline-required no --spacing 0.2 --allowed-rotation 0
```

결과는 항상 `output/YYYYMMDD-HHMMSS_DXF이름/` 아래에 정리된다.

```text
output/
  20260517-223500_Simple-T/
    marker_preview.svg
    marker_report.md
    marker_report.pdf
    report.csv
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
- `size_ratio`: 사이즈별 수량 비율
- `piece_quantity`: 피스별 추가 수량
- `spacing`: 피스 사이 최소 간격
- `allowed_rotation`: 허용 회전 각도
- `grainline_required`: 식서선 필수 여부
- `nap_direction`: 원단 방향성, `one_way`, `two_way`, `none`, `no_nap`, `not_one_way`
- `shrinkage_percent`: 길이 방향 수축률
- `fabric_type`: `woven`, `knit`, `unknown`
- `stretch_direction`: 니트 스트레치 방향
- `seam_allowance`: 시접 포함 여부 객체

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

`nap_direction`이 `one_way`인데 DXF에서 piece-level 식서선을 감지하지 못하면 계산을 중단한다. 이 경우 DXF 식서 레이어를 정리해야 한다.

자세한 배치 기준은 [docs/marker-rules.md](docs/marker-rules.md)를 봐라.

## 시접 기본값

패턴에 시접이 없으면 `seam_allowance`를 `{"status": "excluded"}`로 둔다. `fallback_width`가 없으면 `1/2 inch`를 기준으로 선택 단위별 평균 시접값을 rough 계산에 넣는다.

- `mm`: `12.7`
- `cm`: `1.27`
- `m`: `0.0127`
- `inch`: `0.5`
- `ft`: `0.0416667`
- `yd`: `0.0138889`

이 값은 CAD offset curve가 아니라 평균 확장 추정이다. 생산용 확정 요척으로 보면 안 된다.

## DXF 단위 자동 추정

현재 `estimate`의 고수준 `calculate_marker_yield` 경로는 DXF 좌표 단위를 `auto`로만 처리한다. `--dxf-unit`은 `auto`만 허용된다.

```powershell
python -m fattern estimate input\sample.dxf --fabric-width 150 --unit cm --dxf-unit auto --seam-allowance-status included --nap-direction two_way --grainline-required no
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

MCP 클라이언트가 prompts를 slash UI로 노출하면 `/`를 누른 뒤 `fattern`을 선택하거나 `/fattern`을 실행해서 시작 안내를 볼 수 있다. 서버 쪽에서는 `prompts/list`, `prompts/get`을 지원하고 `fattern`, `fattern-help`, `fattern-estimate` prompt를 제공한다. slash 노출 여부는 클라이언트 지원에 달려 있다.

`/fattern` 안내는 질문지를 강제로 띄우지 않는다. DXF 등록 방식, 필요한 답변, 기본값, tool 호출 순서를 host AI에게 알려주는 MCP prompt다.

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
- R12 legacy `POLYLINE + VERTEX + SEQEND`
- 연결된 `LINE` 조각으로 만든 닫힌 외곽선
- bbox baseline + polygon-aware compact rough marker
- shelf compact, longest-edge-down attempt, overlap geometry cache
- `layer_audit` 기반 DXF 레이어 점검
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
