"""SessionStart hook: in a cloud session, brings ~/.claude up to the latest main.

A cloud environment runs its setup script (skills/dev-setup/reference/cloud.md) once,
snapshots the disk and reuses the snapshot for about seven days, so ~/.claude can lag
main by that much (claude-config#132). This hook fetches main again at the start of
every cloud session. On the desktop it does nothing: CLAUDE_CODE_REMOTE is not set.

As a hook it never blocks and never prints: a SessionStart hook's stdout reaches Claude
as context. It leaves ~/.claude alone when it is not a checkout of claude-config or has
uncommitted changes, so nothing written there by hand is lost.

The sprint orchestrator runs it mid-session with --report, to know whether the refresh
happened (claude-config#192). Then it prints one line and exits with a code:

    refreshed <sha>              exit 0
    not refreshed: <reason>      exit 1

The reasons: not a cloud session, not a claude-config checkout, uncommitted changes,
fetch failed, checkout failed, git timed out, git failed.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = "dolev2/claude-config"
GIT_TIMEOUT_SECONDS = 20


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def checkout_problem(root: Path) -> str | None:
    """Why root may not be refreshed, or None for a clean claude-config checkout."""
    remote = git(root, "remote", "get-url", "origin")
    if remote.returncode != 0 or REPO not in remote.stdout:
        return "not a claude-config checkout"
    if git(root, "rev-parse", "-q", "--verify", "HEAD").returncode != 0:
        return "not a claude-config checkout"
    status = git(root, "status", "--porcelain")
    if status.returncode != 0 or status.stdout != "":
        return "uncommitted changes"
    return None


def refresh(root: Path) -> str | None:
    """Fetch main and check it out; the reason when ~/.claude was left as it was."""
    problem = checkout_problem(root)
    if problem:
        return problem
    if git(root, "fetch", "-q", "--depth", "1", "origin", "main").returncode != 0:
        return "fetch failed"
    checkout = git(root, "checkout", "-q", "-f", "-B", "main", "FETCH_HEAD")
    return None if checkout.returncode == 0 else "checkout failed"


def report(root: Path) -> int:
    """--report: refresh, print the outcome in one line, return the exit code."""
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        problem = "not a cloud session"
    else:
        try:
            problem = refresh(root)
        except subprocess.TimeoutExpired:
            problem = "git timed out"
        except (OSError, subprocess.SubprocessError):
            problem = "git failed"
    if problem:
        print(f"not refreshed: {problem}")
        return 1
    print(f"refreshed {git(root, 'rev-parse', 'HEAD').stdout.strip()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """The hook (no arguments, silent, always 0), or --report."""
    root = Path.home() / ".claude"
    if (sys.argv[1:] if argv is None else argv) == ["--report"]:
        return report(root)
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return 0
    try:
        refresh(root)
    except (OSError, subprocess.SubprocessError):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
