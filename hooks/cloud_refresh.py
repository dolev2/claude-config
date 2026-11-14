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

As the hook, after the refresh it also writes the session's baseline marker: the HEAD of
~/.claude, which is what the session loaded its CLAUDE.md, rules and settings from
(guard_stale_orchestrator.py; claude-config#271). It writes it only when there is none:
SessionStart runs again after /compact, and settings.json is not reloaded then. --report
writes no marker: it runs mid-session, after the session loaded its rules.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = "dolev2/claude-config"
GIT_TIMEOUT_SECONDS = 20
BASELINE_PREFIX = "session-start"
UNSAFE_ID_CHARACTERS = re.compile(r"[^A-Za-z0-9-]")


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def session_marker(prefix: str, session_id: object) -> Path | None:
    """`<tempdir>/claude-hooks/<prefix>-<id>`; None without a usable session_id."""
    if not isinstance(session_id, str):
        return None
    safe_id = UNSAFE_ID_CHARACTERS.sub("", session_id)
    if not safe_id:
        return None
    return Path(tempfile.gettempdir()) / "claude-hooks" / f"{prefix}-{safe_id}"


def read_session_id() -> object:
    """The session_id of the SessionStart event on stdin; None when there is none."""
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    except (OSError, ValueError, AttributeError):
        return None
    return event.get("session_id") if isinstance(event, dict) else None


def write_baseline(root: Path, session_id: object) -> None:
    """Write the HEAD of root to the session's baseline marker, unless one exists."""
    marker = session_marker(BASELINE_PREFIX, session_id)
    if marker is None or marker.exists():
        return
    head = git(root, "rev-parse", "-q", "--verify", "HEAD")
    if head.returncode != 0 or not head.stdout.strip():
        return
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(head.stdout.strip(), encoding="utf-8")


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
            head = "" if problem else git(root, "rev-parse", "HEAD").stdout.strip()
        except subprocess.TimeoutExpired:
            problem = "git timed out"
        except (OSError, subprocess.SubprocessError):
            problem = "git failed"
    if problem:
        print(f"not refreshed: {problem}")
        return 1
    print(f"refreshed {head}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """The hook (no arguments, silent, always 0), or --report."""
    root = Path.home() / ".claude"
    if (sys.argv[1:] if argv is None else argv) == ["--report"]:
        return report(root)
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return 0
    session_id = read_session_id()
    try:
        refresh(root)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        write_baseline(root, session_id)
    except (OSError, subprocess.SubprocessError):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
