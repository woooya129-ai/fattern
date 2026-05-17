# Marker Rules

이 문서는 Fattern v0.3.0의 가요척 산출 기준을 정리한다.

## 목표

Fattern은 DXF 패턴으로 rough marker를 빠르게 만든다. 목적은 견적과 검토용 가요척이다. 생산용 확정 marker, 원단 발주 확정값, 상용 CAD nesting 대체가 아니다.

## 입력 구조

권장 구조:

```text
input/
  sample.dxf
  answers.json
```

실행:

```powershell
python -m fattern estimate
```

출력:

```text
output/YYYYMMDD-HHMMSS_DXF이름/
  marker_preview.svg
  marker_report.md
  result.json
```

자동화에서는 DXF 경로를 직접 줄 수 있다.

```powershell
python -m fattern estimate input\sample.dxf --fabric-width 150 --unit cm --dxf-unit auto --grainline-status unknown --seam-allowance-included no --one-way-fabric no --rotation 0
```

## 단위

사용자는 결과 단위를 아래 중 하나로 고른다.

```text
mm, cm, m, inch, ft, yd
```

`dxf_unit_hint`는 보통 `auto`를 쓴다. DXF가 애매하면 직접 지정한다. 자동 추정은 의류 패턴 크기와 원단 폭을 기준으로 한 휴리스틱이다.

## 원단 폭

질문지는 전세계에서 자주 쓰는 폭을 후보로 준다.

```text
44-45 in / 112-115 cm
54 in / 137 cm
58-60 in / 147-152 cm
108 in / 274 cm
118 in / 300 cm
custom
```

실제 요척은 원단 실측 폭이 우선이다. 프리셋은 질문 보조값이다.

## 식서

식서는 의류 패턴 배치에서 크리티컬하다.

기본값:

```json
"rotation_allowed_degrees": [0]
```

Fattern은 식서를 함부로 돌리지 않는다. `0,180`이나 `0,90,180,270`은 사용자가 명시한 경우에만 쓴다.

`grainline_status` 의미:

```text
present: DXF 또는 사용자가 식서 존재를 확인함
missing: 식서 없음
unknown: 확인 불가
```

원웨이 원단에서 `grainline_status=missing`이면 layout 단계에서 blocker로 중단한다. 식서가 없는데 회전을 허용하면 경고를 낸다.

## 회전

허용 회전은 아래 값만 받는다.

```text
0
0,180
0,90,180,270
```

임의 각도는 아직 지원하지 않는다. 의류 기준에서는 임의 회전이 원단 결, 프린트 방향, 늘어남 방향을 망칠 수 있다.

## 시접

패턴에 시접이 없으면 평균 시접값을 rough 확장에 넣는다.

```text
mm: 10.0
cm: 1.0
m: 0.01
inch: 0.375
ft: 0.03125
yd: 0.0104167
```

이 처리는 정확한 CAD offset curve가 아니다. 넓은 의미의 견적용 보정이다.

## 배치 알고리즘

현재 배치는 아래 절차를 쓴다.

```text
1. bbox baseline 배치
2. polygon-aware bottom-left 후보 탐색
3. gap reuse 후보 탐색
4. local compaction pass
5. 실제 outline 충돌 검증
6. baseline보다 나쁜 detailed 결과는 버림
```

피스가 직사각형이 아니면 outline 기준 후보가 빈 공간을 더 잘 활용할 수 있다. 그래도 최종 결과는 항상 collision과 fabric width 조건을 통과해야 한다.

## UV Atlas에서 차용한 아이디어

Fattern은 UV unwrap 라이브러리 코드를 가져오지 않았다. 적용한 것은 공개 문서에서 확인 가능한 일반 아이디어다.

- 패턴 피스를 UV island처럼 취급한다.
- 크고 까다로운 island를 먼저 배치한다.
- island 사이 margin처럼 `clearance`를 유지한다.
- 회전은 pack 효율보다 사용자 정책이 우선이다.
- 최종 배치는 outline overlap 검증을 통과해야 한다.

v0.3.0에서는 피스 난이도 점수를 `area`, `bbox aspect`, `perimeter`로 잡아 배치 순서 후보에 추가했다. 이건 코드 복사나 라이브러리 의존이 아니라 내부 휴리스틱이다.

참고 자료:

- [xatlas](https://github.com/jpcy/xatlas)
- [Microsoft UVAtlas](https://github.com/microsoft/UVAtlas)
- [Blender UV Editing Manual](https://docs.blender.org/manual/en/5.0/modeling/meshes/uv/editing.html)

## SVG 표시

`marker_preview.svg`에는 아래가 표시된다.

- 원단 경계
- 배치된 피스 outline
- 원단 폭
- marker length
- 식서 상태
- 허용 회전
- 식서 방향 표시

SVG에는 `script`, `foreignObject`, 외부 리소스 링크를 넣지 않는다.

## 제한

- 생산용 확정 요척 아님
- AAMA/ASTM 모든 convention 자동 인식 아님
- 모든 DXF entity 지원 아님
- 곡선 고정밀 flattening 아님
- 프린트 매칭 없음
- 상용 marker CAD 수준 nesting 아님
