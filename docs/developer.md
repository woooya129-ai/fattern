# Developer Guide

This document keeps developer-only setup away from the main README.

## Source Install

```powershell
git clone https://github.com/woooya129-ai/fattern.git
cd fattern
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Source Tree Run Without Install

```powershell
$env:PYTHONPATH = "src"
python -m fattern --help
```

## Commands

```powershell
fattern
fattern ui --open-browser
fattern host --host 127.0.0.1 --port 8765
fattern estimate input\sample.dxf --fabric-width 150 --unit cm --seam-allowance-status included --nap-direction two_way --grainline-required no
fattern mcp-stdio
fattern-mcp
```

`fattern` with no subcommand starts the local Web UI and opens the browser.

## Workspace

First run creates:

```text
input/
output/
config/
```

`config/answers.json` is a starter questionnaire file. Runtime outputs under `input/` and `output/` are ignored by git.

## MCP File Transfer

There are two supported MCP file flows.

```text
estimate_workspace_dxf
  Use this when the DXF is already inside the workspace.
  Input is a workspace-relative path such as input/Simple-T.dxf.
  Absolute paths, .., non-DXF files, and paths outside the workspace are blocked.

register_input_file
  Use this when the host client provides file bytes.
  content_base64 is a JSON transport wrapper for binary DXF bytes.
  It is not encryption and not a security layer.
```

The security boundary is path containment, opaque IDs, file type checks, upload size limits, and artifact allowlists.

## Hosted-Prep Remote MCP

`fattern host` runs the Web UI and enables `/mcp` on the same HTTP server.

```powershell
fattern host --host 127.0.0.1 --port 8765
```

For a public bind, set a token and public URL:

```powershell
$env:FATTERN_REMOTE_MCP_TOKEN = "change-me"
$env:FATTERN_PUBLIC_BASE_URL = "https://example.com"
fattern host --host 0.0.0.0 --port 8765
```

Remote MCP mode disables `estimate_workspace_dxf`. Use `register_input_file` for file bytes, then `calculate_marker_yield`.

Useful endpoints:

```text
/mcp
/hosting/policy
/server.json
/healthz
```

v0.9.0 does not implement production OAuth discovery or token validation. Treat bearer token mode as a deployment guard, not a full multi-user auth system.

## Optional LLM Advisor

The Web UI deterministic Advisor works without API keys. Optional LLM Advisor is enabled only when configured on the server.

OpenAI:

```powershell
$env:FATTERN_LLM_PROVIDER = "openai"
$env:FATTERN_LLM_MODEL = "<model-name>"
$env:OPENAI_API_KEY = "<server-side-key>"
fattern
```

Anthropic:

```powershell
$env:FATTERN_LLM_PROVIDER = "anthropic"
$env:FATTERN_LLM_MODEL = "<model-name>"
$env:ANTHROPIC_API_KEY = "<server-side-key>"
fattern
```

Rules:

- API keys stay on the server.
- Browser JavaScript never receives the key.
- The LLM receives sanitized result context, not raw DXF bytes by default.
- The LLM has no shell or arbitrary file access.

## Tests

```powershell
python -m unittest discover -s tests
```
