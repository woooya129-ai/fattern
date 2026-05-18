# Fattern

[English](README.en.md)

현재 버전: **0.9.0**

Fattern은 DXF 패턴으로 rough marker와 견적용 가요척을 계산하는 도구다. 계산은 deterministic engine이 하고, Web UI와 MCP는 접근 방식만 다르다.

```text
일반 사용자: Web UI
AI 사용자: MCP + Web UI 결과 확인
```

생산 확정용 CAD nesting 대체품은 아니다. `quote_yield`는 견적용 추정값이고, `minimum_yield`는 현재 엔진 배치 기준 최소 소요량이다.

## 설치

Python 3.11 이상 필요.

```powershell
python -m pip install https://github.com/woooya129-ai/fattern/archive/refs/heads/main.zip
```

PyPI 배포 후에는 아래 한 줄로 바꿀 수 있다.

```powershell
python -m pip install fattern
```

## 실행

```powershell
fattern
```

실행하면 로컬 Web UI가 열리고, `input/`, `output/`, `config/` 폴더가 자동으로 만들어진다.

## 폴더

```text
fattern-workspace/
  input/
    DXF 파일을 직접 넣는 곳

  output/
    계산 결과가 자동 저장되는 곳

  config/
    기본 answers.json
```

Web UI에서 파일을 업로드해도 결과는 `output/` 아래에 저장된다.

## 기본 질문지

Web UI 첫 화면에서 아래 값을 입력한다. 모르는 값은 기본값으로 시작할 수 있다.

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
  "seam_allowance": {"status": "included"},
  "allowance_policy": {"mode": "fast_quote"}
}
```

시접이 패턴에 없으면 `seam_allowance.status`를 `excluded`로 바꾼다. 별도 값을 입력하지 않으면 기본 `1/2 inch` 시접을 rough 계산에 적용한다.

## 출력물

결과는 항상 run 폴더로 정리된다.

```text
output/
  20260518-153012_Simple-T/
    marker_preview.svg
    marker_report.md
    marker_report.pdf
    report.csv
    result.json
    run_summary.txt
```

파일 의미:

- `marker_preview.svg`: 배치 그림
- `marker_report.pdf`: 공유용 보고서
- `marker_report.md`: 사람이 읽는 계산 설명
- `report.csv`: 엑셀과 자동화용 배치 결과
- `result.json`: MCP, Codex, Claude Code가 읽기 좋은 전체 결과
- `run_summary.txt`: 가장 짧은 요약

출력 예시:

![Simple-T marker layout output example](docs/assets/simple-t-marker-preview.svg)

## Web UI + MCP

Web UI는 사람이 보는 화면이고, MCP는 AI 클라이언트가 계산을 실행하는 경로다.

```text
Codex 또는 Claude Code
  -> Fattern MCP 호출
  -> calculate_marker_yield 또는 estimate_workspace_dxf
  -> output/run_id 생성
  -> Web UI URL 반환
  -> 사람이 preview 확인
```

MCP high-level 결과에는 `run_id`, `output_dir`, `web_url`, `preview_url`, `report_url`이 포함된다.

## Hosted Web UI + Remote MCP 준비

v0.9.0에는 hosted 준비용 실행 모드가 있다.

```powershell
fattern host --host 127.0.0.1 --port 8765
```

이 모드는 같은 Web UI 서버에 아래 endpoint를 연다.

- `/mcp`: Remote MCP 준비용 HTTP JSON-RPC endpoint
- `/hosting/policy`: 업로드, 보관, 인증, 보안 정책 JSON
- `/server.json`: future MCP registry/package manifest 초안
- `/healthz`: 헬스체크

외부 공개 바인딩은 bearer token이 필요하다.

```powershell
$env:FATTERN_REMOTE_MCP_TOKEN = "change-me"
fattern host --host 0.0.0.0 --public-base-url https://example.com
```

v0.9.0의 `/mcp`는 production OAuth connector가 아니라 준비 단계다. OAuth 2.1 protected-resource metadata, 계정/프로젝트 격리, retention job, quota는 아직 보류다.

자세한 내용은 [Hosted Web UI and Remote MCP](docs/hosting.md)를 본다.

## Advisor

Web UI에는 LLM 없이도 동작하는 Advisor가 있다.

- warning과 blocker를 쉬운 말로 설명
- `cuttable_width`, `seam_allowance`, `nap_direction`, `grainline_required`, `quote_yield` 도움말 표시
- API key가 서버에 설정된 경우에만 선택형 LLM Advisor 사용

API key는 브라우저에 노출하지 않는다. LLM에는 원본 DXF 전체가 아니라 결과 JSON의 요약 정보만 보낸다.

## CLI

고급 사용자는 CLI를 그대로 쓸 수 있다.

```powershell
fattern estimate input\sample.dxf --fabric-width 150 --unit cm --seam-allowance-status included --nap-direction two_way --grainline-required no
```

## MCP

stdio 서버:

```powershell
fattern-mcp
```

또는:

```powershell
fattern mcp-stdio
```

workspace 안 DXF는 `estimate_workspace_dxf`를 우선 사용한다. 첨부 파일이나 원격 MCP 호환 흐름에서는 `register_input_file`을 사용한다.

자세한 개발자 설치와 AI 클라이언트 설정은 아래 문서를 본다.

- [Developer guide](docs/developer.md)
- [AI client guide](docs/ai-clients.md)

## 지원 범위

현재 지원:

- closed `LWPOLYLINE`
- R12 legacy `POLYLINE + VERTEX + SEQEND`
- 연결된 `LINE` 조각의 단순 폐곡선 fallback
- rough marker layout
- `minimum_yield`와 `quote_yield` 분리
- Web UI, CLI, MCP
- hosted-prep Web UI + Remote MCP HTTP endpoint

아직 상용 marker CAD 수준은 아니다.

- 모든 DXF entity 고정밀 변환
- stripe/plaid matching
- fold piece, mirrored pair
- 생산 확정 nesting
- plotter용 multi-page PDF

## 개발

```powershell
python -m unittest discover -s tests
```

## 라이선스

source-available, noncommercial use only.

- [LICENSE](LICENSE)
- [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)
- [NOTICE](NOTICE)
