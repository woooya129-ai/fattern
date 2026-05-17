# Fattern

[English](README.en.md)

DXF 패턴 파일 기반 가요척 산출 CLI 도구.

Fattern은 지원되는 DXF 외곽선을 파싱하고, 피스별 지표를 계산한 뒤, 원단 폭 기준 rough marker 배치를 만들고 SVG 미리보기와 Markdown 리포트를 생성한다.

이 도구는 가요척 산출 보조 도구다. 확정 요척을 보장하지 않고, 상용 마커 시스템을 대체하지 않는다.

## 라이선스 요약

**PolyForm Noncommercial License 1.0.0 + 별도 Commercial License**

이 저장소는 source-available이며, 비상업 사용만 허용한다.

상업 사용, 운영 환경 사용, 유료 컨설팅, 재판매, 호스팅 서비스, 상업 워크플로 통합은 저작권자의 별도 서면 상업 라이선스가 필요하다.

## 기능

- DXF closed LWPOLYLINE, R12 POLYLINE 기반 피스 후보 추출
- 면적, 둘레, bbox 계산
- 원단 폭, 회전 규칙, 피스 간 간격 기준 rough marker 배치
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
python -m fattern estimate tests\fixtures\rectangle_lwpolyline.dxf --fabric-width 10 --unit cm --seam-allowance-included yes --one-way-fabric no --out fattern-output
```

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

## 개발

테스트 실행:

```powershell
python -m unittest discover -s tests
```

현재 테스트 플랜에서 `pytest`는 필수가 아니다.

## 지원 범위

현재 구현은 MVP 범위다.

- closed LWPOLYLINE과 R12 `POLYLINE + VERTEX + SEQEND` 지원
- bottom-left gap reuse + beam search 기반 compact rough marker
- 후보 배치는 좌/하단, 우측 정렬, 하단 정렬, clearance 접촉점을 함께 평가
- DXF layer convention 자동 판정은 제한적
- 복잡한 nesting 최적화, 무늬맞춤, 상용 CAD 호환은 포함하지 않음

## 라이선스 상세

이 프로젝트는 **PolyForm Noncommercial License 1.0.0** 기반 source-available 소프트웨어다.

비상업 목적에서는 라이선스 조건에 따라 사용, 학습, 수정, 공유할 수 있다.

상업 사용, 운영 환경 사용, 유료 컨설팅, 재판매, 호스팅 서비스, 상업 워크플로 통합은 저작권자의 별도 서면 상업 라이선스가 필요하다.

관련 문서:

- [LICENSE](LICENSE)
- [NOTICE](NOTICE)
- [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)

이 프로젝트는 상업 사용을 제한하므로 OSI 승인 오픈소스가 아니다.
