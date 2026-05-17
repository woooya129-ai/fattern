import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


ALLOWED_TRACKED_ROOTS = (
    "docs/",
    "schemas/",
    "src/",
    "tests/",
)

ALLOWED_TRACKED_FILES = {
    ".gitattributes",
    ".gitignore",
    "COMMERCIAL-LICENSE.md",
    "LICENSE",
    "NOTICE",
    "PLAN.md",
    "README.en.md",
    "README.md",
    "fattern.cmd",
    "pyproject.toml",
}

BLOCKED_TRACKED_PATHS = (
    ".github/instructions/",
    ".agents/",
    ".claude/",
    ".codex/",
    ".copilot/",
    ".cursor/",
    ".idea/",
    ".roo/",
    ".vscode/",
    ".windsurf/",
    "docs/worker-reports/",
    "fattern-output/",
    "input/",
    "output/",
)

BLOCKED_TRACKED_PREFIXES = (
    ".aider",
)

BLOCKED_TRACKED_FILES = {
    ".github/copilot-instructions.md",
    "AGENTS.md",
    "AGNETS.md",
    "CLAUDE.md",
    "CODEX.md",
    "COPILOT.md",
    "GEMINI.md",
    "PLAN-REVIEW.md",
    "marker_preview.svg",
    "marker_report.md",
    "result.json",
}

REQUIRED_IGNORE_ENTRIES = {
    ".agents/",
    ".claude/",
    ".codex/",
    ".copilot/",
    ".cursor/",
    ".github/instructions/",
    ".windsurf/",
    ".aider*",
    "AGENTS.md",
    "AGNETS.md",
    "CLAUDE.md",
    "CODEX.md",
    "GEMINI.md",
    "COPILOT.md",
    "PLAN-REVIEW.md",
    "docs/worker-reports/",
    "input/",
    "output/",
    "fattern-output/",
    "result.json",
    "marker_preview.svg",
    "marker_report.md",
}


def git_ls_files() -> list[str]:
    if not (ROOT / ".git").exists():
        raise unittest.SkipTest("repository hygiene checks require a git checkout")
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


class RepositoryHygieneTests(unittest.TestCase):
    def test_tracked_files_stay_inside_product_allowlist(self) -> None:
        unexpected = [
            path
            for path in git_ls_files()
            if path not in ALLOWED_TRACKED_FILES and not path.startswith(ALLOWED_TRACKED_ROOTS)
        ]
        self.assertEqual(unexpected, [])

    def test_ai_and_generated_work_files_are_not_tracked(self) -> None:
        tracked = set(git_ls_files())
        blocked = sorted(
            path
            for path in tracked
            if path in BLOCKED_TRACKED_FILES or path.startswith(BLOCKED_TRACKED_PATHS)
            or path.startswith(BLOCKED_TRACKED_PREFIXES)
        )
        self.assertEqual(blocked, [])

    def test_gitignore_keeps_local_ai_and_output_files_out(self) -> None:
        ignore_entries = {
            line.strip()
            for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        missing = sorted(REQUIRED_IGNORE_ENTRIES - ignore_entries)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
