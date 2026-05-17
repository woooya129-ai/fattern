# Contract Cleanup Notes

v0.4 canonical `calculate_marker_yield` 계약과 사용자-facing 표면(questionnaire, README, CLI, public adapter)이 어긋나는 지점을 정리한다. 기존 테스트는 내부 계약만 보고 있어서 이 갭을 잡지 못했다.

## 처리 현황

2026-05-18 기준 정리 방향:

- Questionnaire/README는 canonical `answers.schema.json` 필드셋으로 맞춘다.
- v0.4 고수준 경로에서는 `grainline_status` user override를 받지 않는다. grainline은 DXF `LINE` 기반 engine 자동감지만 신뢰한다.
- CLI `--grainline-status`는 제거한다. `--nap-direction`, `--spacing`, `--allowed-rotation`, `--fabric-type`, `--shrinkage-percent`, `--seam-allowance-status` canonical 옵션을 노출한다. 기존 `one_way_fabric`, `clearance`, `seam_allowance_included` 계열은 legacy compatibility 입력으로만 남긴다.
- `seam_allowance.status="unknown"`은 schema에서 허용하지 않는다. 사용자는 `included` 또는 `excluded` 중 하나를 명시해야 한다.
- `nap_direction="unknown"`은 schema/default 표현으로는 남아있더라도 `calculate_marker_yield` 실행 전 `NAP_DIRECTION_UNKNOWN` blocker로 중단한다.
- `execute_marker_yield_request` adapter는 지원하지 않는 고수준 필드를 조용히 버리지 않고 blocker로 막는다.
- `fabric_type=knit`이면 stretch 방향 값과 무관하게 현재 engine이 stretch matching을 적용하지 않는다는 warning을 낸다.

이번 보강에서 추가한 회귀 방지:

- README의 `answers.json` 예시가 `answers.schema.json`에 맞는지 검증한다.
- Questionnaire가 canonical 필드를 노출하고 구계약 핵심 필드를 노출하지 않는지 검증한다.
- `nap_direction=unknown` blocker, knit stretch warning, adapter unsupported-field blocker를 검증한다.

## A. Questionnaire가 묻는 필드와 canonical answers schema가 어긋남

위치
- `src/fattern/orchestration/fabric_presets.py:38` - `QUESTIONNAIRE_FIELDS`
- `src/fattern/orchestration/intent.py:210` - `_question_for_field` 매핑
- `src/fattern/schemas/answers.schema.json:7` - canonical required 필드
- `README.md:47-58` - 사용자가 따라 만드는 answers.json 예시

증상
- Questionnaire는 `dxf_unit_hint`, `grainline_status`, `seam_allowance_included`, `seam_allowance_width`, `one_way_fabric`, `rotation_allowed_degrees`, `clearance`를 묻는다.
- Canonical `answers.schema.json`은 `size_ratio`, `spacing`, `allowed_rotation`, `grainline_required`, `nap_direction`, `shrinkage_percent`, `fabric_type`, `seam_allowance`를 required로 요구한다.
- README 예시 그대로 만든 `answers.json`은 canonical schema 관점에서 required 7개가 빠진다. `schema_version` 자체가 없어서 검증 시 첫 줄에서 거부된다.
- CLI는 fallback 로직으로 `clearance`->`spacing`, `rotation_allowed_degrees`->`allowed_rotation`, `seam_allowance_included`+`seam_allowance_width`->`seam_allowance.{status, fallback_width}`를 매핑하지만, 사용자에게는 이중 계약이 보이지 않는다. `nap_direction`, `fabric_type`, `size_ratio`, `shrinkage_percent`는 CLI 기본값(`unknown`/`unknown`/`{}`/`0`)으로 조용히 채워진다.

권장 작업
1. `QUESTIONNAIRE_FIELDS`를 canonical schema 키로 재정렬: `dxf_file`, `fabric_width`, `unit`, `size_ratio`(optional), `piece_quantity`(optional), `spacing`, `allowed_rotation`, `grainline_required`, `nap_direction`, `shrinkage_percent`, `fabric_type`, `stretch_direction`(optional), `seam_allowance`.
2. `_question_for_field`에 누락된 필드(`size_ratio`, `piece_quantity`(이미 있음), `spacing`, `allowed_rotation`(이미 있음), `nap_direction`, `shrinkage_percent`, `fabric_type`, `stretch_direction`, `seam_allowance` 객체)를 추가하고, 구계약 키(`dxf_unit_hint`, `grainline_status`, `one_way_fabric`, `clearance`, `seam_allowance_included`, `seam_allowance_width`)는 LLM 호환 layer가 필요하지 않으면 제거한다.
3. `README.md:47-58` 예시를 canonical schema로 갱신 (`schema_version: "1.0"` 포함). `## 질문지 항목`(README.md:82-95) 텍스트도 함께.
4. `docs/test-plan.md:118` "questionnaire returns fabric_width, unit, dxf_unit_hint, grainline_status, seam allowance, one-way fabric, rotation, clearance questions" 기대치도 새 필드셋에 맞춰 갱신.

## B. `execute_marker_yield_request` adapter가 piece_quantity/shrinkage object를 silent drop

위치
- `src/fattern/orchestration/chain.py:50` - `ADAPTER_UNSUPPORTED_FIELDS = ("size_ratio", "fabric_type")`
- `src/fattern/orchestration/chain.py:317` - `execute_marker_yield_request`
- `src/fattern/orchestration/chain.py:377` - `_high_level_request_blockers`
- `src/fattern/orchestration/__init__.py:3` - public re-export

증상
- adapter는 `size_ratio`, `fabric_type`, `shrinkage_percent>0`에는 blocker를 만들지만, `piece_quantity`, `shrinkage` object(`length_percent`, `width_percent`), `stretch_direction`은 차단도 매핑도 안 한다.
- 호출자가 `piece_quantity={"piece_0001": 2}` 또는 `shrinkage={"length_percent": 3, ...}`를 넘기면 adapter는 그 필드를 그대로 버린 채 ORCH-002 chain을 돌린다. 결과는 "shrinkage 또는 piece quantity가 적용된 것처럼 보이지만 실제로는 무시된" 응답이다.
- `McpToolRegistry._calculate_marker_yield`가 v0.4 고수준 경로(MCP tool `calculate_marker_yield` + CLI)에서 실제로 쓰이고, `execute_marker_yield_request`는 ORCH-002 chain용 호환 wrapper다. 두 경로가 살아있으니 silent drop은 노골적인 위험이다.

권장 작업
1. 첫 번째 선택지(권장): `execute_marker_yield_request`와 `adapt_marker_yield_request`를 `orchestration/__init__.py:3`에서 제거하고, 내부 호출도 제거한 뒤 한 번에 deprecation. v0.4 고수준 경로는 `McpToolRegistry._calculate_marker_yield`로 단일화. 테스트는 `tests/test_orchestration_chain.py`의 adapter 케이스를 삭제하면 된다.
2. 그게 너무 큰 변경이라면 최소 안전장치: `ADAPTER_UNSUPPORTED_FIELDS`(chain.py:50) 튜플에 `piece_quantity`, `shrinkage`, `stretch_direction` 키를 추가하기만 하면 된다. `_high_level_request_blockers`(chain.py:379-387)가 이미 이 튜플을 순회하면서 비어있지 않은 dict/non-null 값에 대해 blocker 메시지를 만들고 있으므로 별도 분기는 불필요하다.
3. 어느 쪽이든 `orchestration/__init__.py:3`에 `# DEPRECATED:` 주석 대신 실제 사용처를 grep해서 호출자 제거 또는 `_calculate_marker_yield` 호출로 전환.

## C. fabric_type=knit + stretch_direction warning 조건이 반대로 걸려있음

위치
- `src/fattern/mcp/tools.py:903`

```python
if arguments.get("fabric_type") == "knit" and arguments.get("stretch_direction") in {None, "unknown"}:
    warnings.append(STRETCH_DIRECTION_NOT_APPLIED)
```

증상
- 메시지 문구는 "stretch matching is not applied in the current marker engine"이다. 즉 "값을 줘도 적용 안 된다"는 안내인데, 조건은 `None`/`unknown`일 때만 발화한다.
- `stretch_direction="lengthwise"`처럼 명시 값을 주면 warning이 안 나오고 결과만 돌아간다. 사용자는 stretch matching이 반영됐다고 오해할 수 있다.

권장 작업
- 조건을 반전: `fabric_type=="knit"`이고 `stretch_direction not in {None}`이면 발화. 또는 fabric_type=knit이면 stretch_direction 값과 무관하게 한 번 발화. 후자가 안전하다.
- 동시에 `FABRIC_TYPE_POLICY_PARTIAL`(tools.py:895)이 이미 발화하고 있으니, 두 warning이 중복으로 안 보이도록 한 쪽에 집약하는 것도 고려.

## D. nap_direction=unknown이 사실상 기본값이 되어 정책이 우회됨

위치
- `src/fattern/cli.py:329-332` - CLI가 `nap_direction`을 answers에서 못 찾으면 `_nap_direction_from_one_way_fabric(one_way_fabric)`로 채움
- `src/fattern/cli.py:466-471` - `one_way_fabric is None`이면 `"unknown"` 반환
- `src/fattern/schemas/answers.schema.json:86-90` - `nap_direction` default도 `"unknown"`
- `src/fattern/mcp/tools.py:870-874` - `nap_direction=="one_way"`만 180 rotation 차단. `"unknown"`은 차단 대상이 아니다.

증상
- 사용자가 `one_way_fabric`도, `nap_direction`도 명시하지 않으면 `nap_direction="unknown"`으로 채워져 `calculate_marker_yield`까지 들어간다.
- `"unknown"`은 정책 차단을 받지 않는다. 그래서 회전 정책, grainline missing 정책이 약화된 상태로 계산이 진행된다.
- `PLAN.md:55-60` "식서 미확인 상태에서 원웨이 원단이면 blocker", "fabric_type=woven 또는 grainline_required=true면 grainline missing은 blocker"는 살아있지만, nap_direction=unknown 자체에는 가드가 없다.

권장 작업
- CLI는 `nap_direction`을 `"unknown"`으로 자동 채우지 말고, `one_way_fabric`이 명시되지 않으면 사용자에게 묻거나 보수적 기본을 쓴다. `"unknown"`은 schema-only 상태로 두고 calculate_marker_yield 진입 시 blocker 또는 명시적 warning을 띄운다.
- 또는 `_validate_marker_yield_request`(tools.py:837)에 `nap_direction=="unknown"`이면 `NAP_DIRECTION_UNKNOWN` blocker를 추가한다. PLAN.md에서 `nap_direction`은 정책 결정 인자이므로 unknown 통과는 명시 정책이 없는 한 위험.
- 주의: PLAN.md:60은 `nap_direction=one_way` 정책만 명시한다. CLI가 미지정 입력을 `"two_way"` 같은 값으로 자동 채우는 건 새 정책 도입이므로 PLAN.md 갱신을 함께 해야 한다. 보수적 기본을 정하기 어렵다면 missing field 처리(clarification 요구)가 안전하다.

## E. CLI `--grainline-status` 인자가 dead code

위치
- `src/fattern/cli.py:62-67` - argparse 정의
- `_estimate`(cli.py:94)에서 `args.grainline_status`를 한 번도 읽지 않음 (grep 확인)

증상
- 사용자에게는 `--grainline-status present|missing|unknown` 옵션이 노출되지만 실제로는 noop이다.
- README.md:22 예시도 `--grainline-status unknown`을 포함한다. 동작하지 않는다는 사실이 documented되지 않았다.

권장 작업
- 둘 중 하나:
  1. 인자 정의(cli.py:62-67) 제거. README.md:22의 예시도 갱신.
  2. canonical schema에 `grainline_status`가 없는 이상 `--grainline-status`는 `user_intent.rules.grainline_status`로만 의미가 있다. high-level path는 `grainline_required` boolean과 engine 자동감지(`piece.has_grainline`)로 충분하므로 1번이 깔끔.

## F. grainline_status가 user-intent에는 있지만 answers schema에는 없음

위치
- `src/fattern/orchestration/intent.py:147` - `rules.grainline_status` 정규화
- `src/fattern/schemas/answers.schema.json` - `grainline_status` 키 없음
- `src/fattern/mcp/tools.py` `calculate_marker_yield` 입력 schema도 grainline_status를 받지 않음(grep로 확인 가능)

증상
- ORCH-001 UserIntent는 grainline_status를 받고, ORCH-002 chain은 `_grainline_status`(chain.py:651)에서 user intent 값을 우선한다.
- v0.4 고수준 경로는 grainline_status를 받지 않고 `extract_pattern_pieces` 자동감지 결과만 사용한다.
- 사용자가 "DXF에 식서선이 없다는 걸 미리 알고 있으니 grainline_status=missing으로 빠르게 fail" 하려는 use case는 v0.4 경로에서 못 한다.

권장 작업
- 의도가 "v0.4에서는 grainline은 engine 자동감지만 신뢰한다"라면, questionnaire/CLI에서 grainline_status를 묻지 말고 위 A 항목 정리 시 동시에 제거.
- 의도가 "user override를 허용한다"라면 canonical schema와 calculate_marker_yield tool schema에 `grainline_status`를 추가하고 `_calculate_marker_yield`에서 `extract_pattern_pieces` 호출 시 user 값을 우선 적용.

## G. seam_allowance.status="unknown"이 schema-valid이지만 즉시 blocker

위치
- `src/fattern/schemas/answers.schema.json:128-131` - `enum: ["included", "excluded", "unknown"]`
- `src/fattern/mcp/tools.py:876-881` - `status=="unknown"`이면 `SEAM_ALLOWANCE_STATUS_UNKNOWN` blocker

증상
- 사용자가 schema-valid한 answers.json (`seam_allowance: {"status": "unknown"}`)을 만들면 항상 blocker로 떨어진다. schema가 허용하는 값을 tool이 즉시 거부하는 비대칭.
- canonical 예시(`PLAN.md:92-95`)는 `status: "included"`만 보여주므로 사용자가 unknown을 의식적으로 쓸 가능성은 낮지만, 모범 답안 없이 questionnaire를 보고 만들면 unknown을 고르기 쉽다.

권장 작업
- answers schema enum에서 `"unknown"`을 빼고 questionnaire에서도 `included`/`excluded` 둘 중 하나로 강제한다. 명시 거부가 사용자에게 더 정직하다.
- 또는 `_validate_marker_yield_request`에서 status=unknown을 blocker 대신 warning으로 낮추고, `seam_allowance_width=0` 또는 engine `default_seam_allowance_width`로 fallback하는 정책을 추가한다. 단 이 경우 "seam allowance unknown -> 평균 시접 적용" 정책을 PLAN.md에 명시.

## 우선순위 제안

1. **먼저 고칠 것 (사용자가 README/questionnaire를 따라 만든 answers.json이 작동하지 않음)**
   - A. Questionnaire/README 갱신
   - E. CLI `--grainline-status` dead 인자 정리
   - G. `seam_allowance.status="unknown"` 비대칭 (schema와 tool 중 한쪽 정렬)

2. **다음 (silent drop으로 잘못된 결과를 자신감 있게 반환)**
   - B. `execute_marker_yield_request` adapter 제거 또는 차단 강화
   - C. stretch_direction warning 반전
   - D. nap_direction=unknown 기본 차단

3. **정책 결정이 필요한 것**
   - F. grainline_status를 v0.4 경로에서 인정할지 결정

## 회귀 방지

위 작업과 함께 추가하면 좋은 테스트:
- `tests/test_schemas.py`에 "README JSON example validates against answers.schema" 케이스.
- `tests/test_cli.py`에 "minimal canonical answers.json runs estimate end-to-end" 케이스 (현재는 구계약 answers로 통과 중일 가능성).
- `tests/test_mcp_tools.py`에 "nap_direction=unknown -> blocker" 케이스 (D 적용 후).
- `tests/test_orchestration_chain.py`에 "piece_quantity nonempty -> adapter blocker" 케이스 (B-2 적용 후) 또는 adapter 제거 시 관련 케이스 삭제.
