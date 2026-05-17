# Repository Hygiene Law

This repository tracks only product files.

## Tracked Content

Allowed tracked content:

- product source code under `src/`
- tests and fixtures under `tests/`
- JSON schemas under `schemas/`
- official project documentation under `docs/`
- root project files required for packaging, licensing, and usage

Root project files currently allowed:

- `.gitattributes`
- `.gitignore`
- `COMMERCIAL-LICENSE.md`
- `LICENSE`
- `NOTICE`
- `PLAN.md`
- `README.en.md`
- `README.md`
- `fattern.cmd`
- `pyproject.toml`

Any new tracked root file must be intentionally classified as product code, test, schema, official documentation, packaging, licensing, or usage material.

## Never Track

Never commit AI working files, assistant instructions, role cards, prompts, task packets, intermediate notes, generated worker reports, local tool state, editor state, or CLI output artifacts.

Blocked examples:

- `.agents/`
- `.claude/`
- `.codex/`
- `.cursor/`
- `.copilot/`
- `.windsurf/`
- `AGENTS.md`
- `AGNETS.md`
- `CLAUDE.md`
- `CODEX.md`
- `GEMINI.md`
- `COPILOT.md`
- `PLAN-REVIEW.md`
- `docs/worker-reports/`
- `input/`
- `output/`
- `fattern-output/`
- `result.json`
- `marker_preview.svg`
- `marker_report.md`

If a file exists only to tell an AI assistant what to do, record an AI run, or hold temporary output, it is local-only.

## Before Risky Git Work

Before history rewrite, rebase, reset, force push, mass rename, or dependency upgrade:

1. Run `git status --short --branch`.
2. Preserve current work with a stash, temporary branch, or intentional commit.
3. Verify the working tree is clean or that the remaining dirty files are unrelated.
4. Run the risky operation.
5. Restore preserved work.
6. Re-run `git status --short --branch`.

Do not rewrite history with mixed uncommitted work unless every dirty file has been classified.

## Before Commit Or Push

Before commit or push:

1. Run `git status --short`.
2. Run `git ls-files`.
3. Confirm every tracked file is product source, test, schema, official documentation, packaging, licensing, or usage material.
4. Run `python -m unittest tests.test_repository_hygiene`.

The hygiene test is the gate. If it fails, either remove the tracked file or update this policy intentionally.
