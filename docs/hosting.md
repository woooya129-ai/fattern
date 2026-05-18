# Hosted Web UI and Remote MCP

Version: 0.9.0

This document defines the v0.9.0 preparation boundary for hosted Web UI and remote MCP.

## Goal

Fattern keeps three routes:

```text
General user:
  Web UI upload

AI-assisted local user:
  stdio MCP + Web UI result links

Hosted/remote candidate:
  hosted Web UI + /mcp HTTP endpoint
```

The hosted route is for access, not for changing the calculation engine. The deterministic engine remains the source of truth.

## Official Constraints

Remote MCP must be treated differently from local stdio MCP.

- MCP Streamable HTTP uses an HTTP endpoint such as `/mcp` and exchanges JSON-RPC over POST. Reference: https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- MCP servers should validate `Origin`, bind local servers to localhost by default, and implement authentication for HTTP connections. Reference: https://modelcontextprotocol.io/specification/draft/basic/transports
- Published remote MCP servers must be publicly reachable and should declare `streamable-http` remotes. Reference: https://modelcontextprotocol.io/registry/remote-servers
- MCP authorization for production HTTP transports is OAuth-based and uses protected resource metadata. Reference: https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization
- Claude custom remote connectors connect from Anthropic cloud infrastructure, not from the user's local device. Reference: https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp
- OpenAI remote MCP support expects a public `server_url`; tool calls can require approval and carry third-party data risk. Reference: https://developers.openai.com/api/docs/guides/tools-connectors-mcp

## v0.9.0 Command

Local hosted-prep mode:

```powershell
fattern host --host 127.0.0.1 --port 8765
```

Public-bind preparation:

```powershell
$env:FATTERN_REMOTE_MCP_TOKEN = "change-me"
$env:FATTERN_PUBLIC_BASE_URL = "https://example.com"
fattern host --host 0.0.0.0 --port 8765
```

Public bind without a token is blocked.

## Endpoints

```text
/                Web UI
/estimate        Web UI upload action
/runs/...        persisted run outputs
/advisor         optional server-side LLM Advisor
/mcp             remote-MCP-prep HTTP JSON-RPC endpoint
/hosting/policy  explicit hosted policy JSON
/server.json     draft remote MCP manifest
/healthz         health check
```

## Remote MCP Contract

`/mcp` accepts JSON-RPC POST and returns `application/json`.

Implemented:

- `initialize`
- `ping`
- `tools/list`
- `tools/call`
- `prompts/list`
- `prompts/get`

Not implemented in v0.9.0:

- SSE response streams
- OAuth protected-resource metadata
- dynamic client registration
- account/project isolation
- quota and billing
- remote connector directory submission

`GET /mcp` returns `405` until SSE streaming is implemented.

## Tool Policy

Local stdio MCP can use:

```text
estimate_workspace_dxf
```

Remote MCP hides that tool and blocks direct calls to it. Reason: a cloud-hosted connector must not read arbitrary local workspace paths.

Remote file flow:

```text
create_job
register_input_file
calculate_marker_yield
```

`register_input_file.content_base64` is only JSON transport encoding for binary DXF bytes. It is not encryption.

## Data Policy

v0.9.0 local behavior:

- raw DXF is processed by the deterministic engine
- outputs are saved under `output/run_id/`
- local files remain until the user deletes them
- optional LLM Advisor receives sanitized result context, not raw DXF bytes by default

Hosted production must define before public launch:

- user account and project isolation
- raw DXF retention period
- output retention period
- deletion job
- per-user upload limit
- audit log policy
- BYOK or server-key policy for Advisor

## Security Boundary

v0.9.0 guards:

- localhost default bind
- bearer token required for public bind
- `Origin` validation on `/mcp`
- request size limits
- workspace path tool disabled for remote MCP
- artifact allowlist
- path containment for local workspace tools

Remaining blockers:

- replace bearer-token guard with production OAuth resource server behavior
- publish protected resource metadata
- validate access-token audience
- add per-user storage isolation
- add rate limits and quota
- document hosted data residency and deletion SLA

## Release Decision

v0.9.0 is "ready to test remote MCP shape", not "ready for public hosted service".

Do not market it as a production connector until OAuth, retention, quota, and tenant isolation are implemented.
