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
