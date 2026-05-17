# Fattern

[English](README.en.md)

DXF 패턴 파일 기반 가요척 산출 CLI 도구.

Fattern은 **FAST + PATTERN = FATTERN**이라는 의미다.

Fattern은 지원되는 DXF 외곽선을 파싱하고, 피스별 지표를 계산한 뒤, 원단 폭 기준 rough marker 배치를 만들고 SVG 미리보기와 Markdown 리포트를 생성한다.

이 도구는 가요척 산출 보조 도구다. 확정 요척을 보장하지 않고, 상용 마커 시스템을 대체하지 않는다.

## 라이선스 요약

**PolyForm Noncommercial License 1.0.0 + 별도 Commercial License**

이 저장소는 source-available이며, 비상업 사용만 허용한다.

상업 사용, 운영 환경 사용, 유료 컨설팅, 재판매, 호스팅 서비스, 상업 워크플로 통합은 저작권자의 별도 서면 상업 라이선스가 필요하다.

## 기능

- DXF closed LWPOLYLINE, R12 POLYLINE 기반 피스 후보 추출
- 면적, 둘레, bbox, 원본 polygon outline 계산
- 원단 폭, 회전 규칙, 피스 간 간격 기준 polygon-aware rough marker 배치
- 의상 DXF 좌표 단위 autoscale 추정과 단위 변환
- seam allowance 미포함 패턴에 평균 seam allowance를 적용한 rough marker 산출
- overlap, fabric width, grainline 규칙 검증
- SVG 미리보기 생성
- Markdown 리포트 생성
- MCP stdio server와 orchestration regression 테스트 포함

## CLI

저장소 루트에서 실행:

```powershell
python -m fattern --help
```

예시:

```powershell
python -m fattern estimate tests\fixtures\rectangle_lwpolyline.dxf --fabric-width 10 --unit cm --seam-allowance-included yes --one-way-fabric no
```

기본 출력 폴더는 `output`이다. 결과는 `marker_preview.svg`, `marker_report.md`, `result.json`으로 정리된다.

DXF 좌표 단위는 기본값 `--dxf-unit auto`로 의상 패턴 크기 기준에서 추정한다. 애매하면 `--dxf-unit mm`, `--dxf-unit cm`, `--dxf-unit inch`로 직접 지정한다.

seam allowance가 없는 패턴은 `--seam-allowance-included no`로 실행한다. 기본 평균값은 단위별로 `cm=1.0`, `mm=10.0`, `inch=0.375`를 쓴다.

```powershell
python -m fattern estimate tests\fixtures\rectangle_lwpolyline.dxf --fabric-width 10 --unit cm --seam-allowance-included no --one-way-fabric no
```

기본값 대신 직접 지정하려면 `--seam-allowance`를 함께 넘긴다.

```powershell
python -m fattern estimate tests\fixtures\rectangle_lwpolyline.dxf --fabric-width 10 --unit cm --seam-allowance-included no --seam-allowance 0.8 --one-way-fabric no
```

## 원단 폭 후보

전세계 의류 패턴 실무 기준으로 단일 표준값 하나가 아니라 자주 쓰이는 폭 후보를 질문지로 제시한다.

- `44-45 in / 112-115 cm`: 기본 의류, 퀼팅 코튼, 소품
- `54 in / 137 cm`: 의류, 업홀스터리, 홈데코에서 자주 쓰는 중간 폭
- `58-60 in / 147-152 cm`: 니트, 원피스, 코트 등 넓은 의류 원단
- `108 in / 274 cm`: 퀼트 backing, 침구, 대형 패널
- `118 in / 300 cm`: 커튼, sheer drapery 같은 초광폭 원단
- `custom`: 실제 원단 폭 직접 입력

Windows 로컬 래퍼:

```powershell
.\fattern.cmd --help
```

## MCP stdio

MCP 클라이언트에서 stdio 서버로 실행할 수 있다.

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

DXF 파일 경로는 MCP tool input으로 받지 않는다. 클라이언트는 `register_input_file`에 `file_name`과 `content_base64`를 넘겨 `file_id`를 받은 뒤 `parse_dxf`를 호출해야 한다.

MCP 클라이언트는 먼저 `get_estimation_questionnaire`를 호출해 작업 질문지를 받을 수 있다. 질문 항목은 아래 순서다.

```text
dxf_file
fabric_width
unit
dxf_unit_hint
seam_allowance_included
seam_allowance_width
one_way_fabric
rotation_allowed_degrees
clearance
```

## 개발

테스트 실행:

```powershell
python -m unittest discover -s tests
```

현재 테스트 플랜에서 `pytest`는 필수가 아니다.

## 지원 범위

현재 구현은 MVP 범위다.

- closed LWPOLYLINE과 R12 `POLYLINE + VERTEX + SEQEND` 지원
- bottom-left gap reuse + beam search 기반 polygon-aware compact rough marker
- 후보 배치는 좌/하단, 우측 정렬, 하단 정렬, 1배/2배 clearance 접촉점을 함께 평가
- 초벌 배치 후 피스를 하나씩 다시 넣어보는 local compaction pass로 남는 공간을 재검토
- polygon 충돌검사는 edge bounding-box pruning으로 필요한 선분쌍만 정밀 검사
- bbox baseline을 항상 함께 평가해서 detailed 탐색 결과가 기존 보수 배치보다 나쁘면 버림
- SVG 미리보기는 bbox 사각형이 아니라 원본 closed polyline 외곽선을 배치된 위치에 렌더링
- polygon compact 후보가 원본 outline 최종검증을 통과하지 못하면 `BBOX_FALLBACK_USED` warning과 함께 보수적 bbox 배치를 사용
- seam allowance는 평균값을 기준으로 outline을 확장하는 rough 추정이며, CAD의 정확한 offset curve 계산은 아님
- DXF autoscale은 의상 패턴 크기 기준 휴리스틱이며, 애매한 도면은 사용자가 `dxf_unit_hint`로 직접 지정해야 함
- DXF layer convention 자동 판정은 제한적
- 임의 각도 회전, 곡선 flattening 고도화, 무늬맞춤, 상용 CAD 수준 nesting 최적화는 포함하지 않음

## 라이선스 상세

이 프로젝트는 **PolyForm Noncommercial License 1.0.0** 기반 source-available 소프트웨어다.

비상업 목적에서는 라이선스 조건에 따라 사용, 학습, 수정, 공유할 수 있다.

상업 사용, 운영 환경 사용, 유료 컨설팅, 재판매, 호스팅 서비스, 상업 워크플로 통합은 저작권자의 별도 서면 상업 라이선스가 필요하다.

관련 문서:

- [LICENSE](LICENSE)
- [NOTICE](NOTICE)
- [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)

이 프로젝트는 상업 사용을 제한하므로 OSI 승인 오픈소스가 아니다.
