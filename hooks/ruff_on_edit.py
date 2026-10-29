"""PostToolUse hook: formats a .py file that Write or Edit touched, reports lint left.

Wired in settings.json for the Write, Edit and MultiEdit tools (claude-config#64), run
by python3 or python, whichever exists, from $HOME/.claude/hooks/.

Only `ruff format` changes the file. `ruff check` runs without --fix: an automatic fix
can delete an import the next edit is about to use, so the errors go back to Claude as
context instead, and Claude fixes them itself (#64, question 1).

The tool already wrote the file, so there is nothing to block: the hook always exits 0.
It does nothing when ruff is missing, when no ruff settings sit above the file, or when
ruff itself fails.
"""

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

from shell_commands import edit_target, read_event

PYTHON_SUFFIXES = (".py", ".pyi")
RUFF_CONFIG_NAMES = ("ruff.toml", ".ruff.toml")
RUFF_TIMEOUT_SECONDS = 20


def has_ruff_section(pyproject: Path) -> bool:
    """True when pyproject.toml holds a [tool.ruff] table."""
    try:
        settings = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return "ruff" in settings.get("tool", {})


def find_ruff_config(path: Path) -> Path | None:
    """The folder of the nearest ruff settings above path, up to the git root."""
    for folder in path.parents:
        if any((folder / name).is_file() for name in RUFF_CONFIG_NAMES):
            return folder
        pyproject = folder / "pyproject.toml"
        if pyproject.is_file() and has_ruff_section(pyproject):
            return folder
        if (folder / ".git").exists():
            return None
    return None


def run_ruff(ruff: str, arguments: list[str], cwd: Path) -> str | None:
    """Run ruff with arguments in cwd; its output, or None when it fails to run."""
    try:
        result = subprocess.run(
            [ruff, *arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=RUFF_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode not in (0, 1):
        return None
    return result.stdout


def format_and_check(path: Path) -> str | None:
    """Format the file; return the lint errors left, or None when there are none."""
    if path.suffix.lower() not in PYTHON_SUFFIXES or not path.is_file():
        return None
    ruff = shutil.which("ruff")
    config_folder = find_ruff_config(path)
    if ruff is None or config_folder is None:
        return None
    # --force-exclude keeps the repo's `exclude` in force for a file named on the line.
    if run_ruff(ruff, ["format", "--force-exclude", str(path)], config_folder) is None:
        return None
    check_arguments = ["check", "--force-exclude", "--output-format", "concise"]
    report = run_ruff(ruff, [*check_arguments, str(path)], config_folder)
    if not report or "All checks passed" in report:
        return None
    return report.strip()


def lint_feedback(report: str) -> str:
    """The JSON that hands the lint errors to Claude as context, without blocking."""
    message = (
        "ruff check found problems in the file you just edited (the hook formats the "
        "file but does not fix lint). Fix them:\n" + report
    )
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }
    return json.dumps(output, ensure_ascii=False)


def main() -> int:
    """Read the tool call from stdin, format its file, report lint; always return 0."""
    event = read_event(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    if event is None:
        return 0
    try:
        path = edit_target(event)
        report = format_and_check(path) if path is not None else None
    except (OSError, ValueError):
        return 0
    if report:
        sys.stdout.buffer.write(lint_feedback(report).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
