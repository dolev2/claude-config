"""SessionStart hook: in a cloud session, brings ~/.claude up to the latest main.

A cloud environment runs its setup script (skills/dev-setup/reference/cloud.md) once,
snapshots the disk and reuses the snapshot for about seven days, so ~/.claude can lag
main by that much (claude-config#132). This hook fetches main again at the start of
every cloud session. On the desktop it does nothing: CLAUDE_CODE_REMOTE is not set.

It never blocks and never prints: a SessionStart hook's stdout reaches Claude as
context. It leaves ~/.claude alone when it is not a checkout of claude-config or has
uncommitted changes, so nothing written there by hand is lost.
"""

import os
import subprocess
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


def is_clean_checkout(root: Path) -> bool:
    """True when root is a claude-config checkout with a commit and no local changes."""
    remote = git(root, "remote", "get-url", "origin")
    if remote.returncode != 0 or REPO not in remote.stdout:
        return False
    if git(root, "rev-parse", "-q", "--verify", "HEAD").returncode != 0:
        return False
    status = git(root, "status", "--porcelain")
    return status.returncode == 0 and status.stdout == ""


def refresh(root: Path) -> bool:
    """Fetch main and check it out; False when ~/.claude was left as it was."""
    if not is_clean_checkout(root):
        return False
    if git(root, "fetch", "-q", "--depth", "1", "origin", "main").returncode != 0:
        return False
    return git(root, "checkout", "-q", "-f", "-B", "main", "FETCH_HEAD").returncode == 0


def main() -> None:
    if os.environ.get("CLAUDE_CODE_REMOTE") != "true":
        return
    try:
        refresh(Path.home() / ".claude")
    except (OSError, subprocess.SubprocessError):
        pass


if __name__ == "__main__":
    main()
