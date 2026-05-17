# Security Checklist

## ID와 경로

- 모든 외부 입력 ID는 opaque ID로만 처리한다.
- `job_id`, `file_id`, `piece_set_id`, `metrics_id`, `layout_id`는 정규식 allowlist와 최대 길이를 둔다.
- 실제 파일은 서버 내부 mapping으로만 찾는다.
- tool input의 절대경로, 상대경로, URI, UNC path, drive letter는 blocker로 차단한다.
- symlink, junction, hardlink, Windows ADS 경유 접근을 차단한다.
- 파일 접근 전 canonical realpath를 계산하고 job workspace root 하위인지 확인한다.

## 파일 입력

- 허용 확장자는 `.dxf`, `.json`으로 제한한다.
- 확장자 외 type 검증을 둔다.
- 최대 파일 크기, DXF entity 수, 처리 시간 제한을 둔다.
- MCP 입력 파일 등록은 경로가 아니라 `file_name`과 `content_base64`만 받는다.
- archive 입력은 MVP에서 금지한다.

## MCP 서버

- 기본 transport는 stdio 또는 localhost 전용이다.
- `0.0.0.0` bind를 금지한다.
- 외부 네트워크 접근과 임의 client 접근을 금지한다.
- subprocess는 기본 금지한다.
- subprocess가 필요한 경우 allowlisted executable, `shell=false`, 고정 cwd, env allowlist, timeout, 출력 크기 제한을 둔다.

## Artifact Export

- `export_artifacts`는 manifest 기반 allowlist만 내보낸다.
- workspace 내부 artifact만 export한다.
- archive 생성 시 zip-slip 방지 검증을 통과해야 한다.
- log, 내부 설정, 임시 파일은 export 대상에서 제외한다.
- export로 생성된 archive artifact는 중첩 zip export 정책이 확정되기 전까지 재export 대상에서 제외해야 한다.
- archive input 업로드는 금지하고, 내부 생성 archive도 size/quota 정책 없이 반복 export하지 않는다.
- `register_artifact`는 파일 쓰기 전에 최대 byte 제한을 적용해야 한다.
- artifact size limit 미구현 상태에서는 대형 SVG/Markdown/zip 생성 경로를 blocked risk로 취급한다.

## MCP Schema Drift

- `schemas/mcp-tools.schema.json`과 Python `TOOL_SCHEMAS`는 tool name, required, default, enum, const, type, min/max, uniqueItems, items 계약이 일치해야 한다.
- `$ref`로 공유되는 opaque ID schema도 Python schema와 동일한 pattern, minLength, maxLength를 유지해야 한다.
- schema/code drift가 발견되면 schema 또는 Python 계약 중 하나를 임의 기준으로 보정하지 말고 director 결정 후 같이 수정한다.

## 출력 Escaping

- SVG/Markdown에 들어가는 사용자 입력, DXF layer명, piece명은 escape한다.
- SVG `script`, `foreignObject`, external href, remote resource 참조는 금지한다.
- DXF metadata는 untrusted text로 취급한다.

## Logging

- tool call log는 내부 경로, 사용자 note, stack trace, 환경변수, 민감정보를 redaction한다.
- tool error response는 raw exception message를 그대로 노출하지 않고 public message만 redaction 후 반환한다.
- persistent log를 추가할 때는 redaction된 public message만 저장하고 raw stack trace, env, workspace root는 저장하지 않는다.
- log 보관 기간과 접근 권한을 명시한다.
- error response는 내부 경로, workspace root, stack trace, env를 노출하지 않는다.

## Job Workspace

- job별 isolated workspace를 생성한다.
- workspace quota, TTL, cleanup 정책을 둔다.
- 동시 실행 lock 또는 atomic write 정책을 둔다.
- partial artifact는 실패 상태로 표시하고 export 대상에서 제외한다.
