"""PreToolUse hook: a sub-agent in parallel work edits only the files of its own part.

In dev-code's parallel work (claude-config#82), the main session writes the parts file
`<git-common-dir>/parallel-parts.json` (each part and its path prefixes), and every
agent registers its part in `<its git dir>/parallel-part`. From then on, an agent's edit
outside its part's prefixes is blocked here, and the agent writes the change as a
request to the main session in its report instead.

Wired in settings.json for Edit, Write, MultiEdit and NotebookEdit. Exit 0 with no
output means no decision; exit 2 blocks the call, and stderr is the reason Claude sees.

The agent is found by `agent_id` in the hook input, and the repo by the folder of the
edited file, never by `cwd`, which the agent's `cd` moves. Reading stays open: only
edit tools are judged. Anything that goes wrong (no git, broken JSON, odd input) lets
the call through. Writes from shell commands (`sed -i`, `>`) are not caught: this
guards against mistakes, not a security boundary.
"""

import codecs
import json
import os
import subprocess
import sys
from pathlib import Path

from shell_commands import edit_target, read_event

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
PARTS_FILE = "parallel-parts.json"
REGISTRATION_FILE = "parallel-part"
GIT_TIMEOUT_SECONDS = 5
REQUEST_LINE = (
    'לא עורכים: ממשיכים בחלק שלך, וכותבים את השינוי כ"בקשה לסשן הראשי" בדוח שלך'
    " (הקובץ, השינוי, ולמה).\n"
)
GIT_DIR_REASON = (
    "{path} נמצא בתיקיית ה-git המשותפת: קובץ החלקים וההרשמה של העבודה במקביל"
    " שייכים לסשן הראשי.\n" + REQUEST_LINE
)
OUTSIDE_PART_REASON = (
    "{path} מחוץ לחלק `{part}` שלך בעבודה במקביל.\n"
    "הקידומות של החלק: {prefixes}.\n" + REQUEST_LINE
)
OTHER_WORKTREE_REASON = (
    "{path} נמצא בעותק אחר של הריפו, לא בעותק שלך (חלק `{part}`).\n"
    "סוכן כותב רק בעותק שלו, בקידומות: {prefixes}.\n" + REQUEST_LINE
)
UNKNOWN_PART_REASON = (
    "ההרשמה שלך מצביעה על החלק `{part}`, שלא קיים בקובץ החלקים.\n"
    "החלקים הקיימים: {parts}.\n"
    'מתקנים את ההרשמה (`echo <part> > "$(git rev-parse --git-dir)/parallel-part"`)'
    ", או מדווחים לסשן הראשי.\n"
)


def is_inside(path: Path, root: Path) -> bool:
    """True when path is root or below it, ignoring case where the OS does."""
    path_text = os.path.normcase(str(path))
    root_text = os.path.normcase(str(root))
    return path_text == root_text or path_text.startswith(
        root_text.rstrip(os.sep) + os.sep
    )


def existing_folder(path: Path) -> Path:
    """The nearest folder that exists, starting from the parent of path."""
    folder = path.parent
    while not folder.is_dir() and folder != folder.parent:
        folder = folder.parent
    return folder


def git_common_dir(folder: Path) -> Path | None:
    """The shared git folder of the repo that holds folder; None outside any repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(folder), "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        return None
    return (folder / output).resolve()


def read_text(path: Path) -> str | None:
    """The file's text without surrounding whitespace; None when it cannot be read.

    Windows PowerShell's `echo x > file` writes UTF-16 with a BOM, and `Out-File`
    UTF-8 with one, so both BOMs are read rather than taken as part of the text.
    """
    try:
        data = path.read_bytes()
        encoding = (
            "utf-16"
            if data[:2] in (codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)
            else "utf-8-sig"
        )
        return data.decode(encoding).strip()
    except (OSError, ValueError):
        return None


def load_parts(common: Path) -> dict[str, list[str]] | None:
    """Each part's path prefixes from the parts file; None when missing or malformed."""
    text = read_text(common / PARTS_FILE)
    try:
        data = json.loads(text) if text else None
    except ValueError:
        return None
    parts = data.get("parts") if isinstance(data, dict) else None
    if not isinstance(parts, dict):
        return None
    for prefixes in parts.values():
        if not isinstance(prefixes, list):
            return None
        if not all(isinstance(prefix, str) for prefix in prefixes):
            return None
    return parts


def agent_worktree(agent_git_dir: Path) -> Path | None:
    """The agent's worktree folder, from the `gitdir` file that points at its .git.

    The pointer is relative to the git dir when `worktree.useRelativePaths` is on.
    """
    pointer = read_text(agent_git_dir / "gitdir")
    if not pointer:
        return None
    return (agent_git_dir / pointer).resolve().parent


def matches_part(relative: str, prefixes: list[str]) -> bool:
    """True when the POSIX path starts with one of the prefixes.

    A prefix is the start of a path, as in dev-code's final `git diff --name-only`
    check (claude-config#233): `reference/issue-lifecycle` covers both pages of it,
    and a folder is written with a trailing `/` so that `hooks/` misses `hooks_old/`.
    """
    return any(relative.startswith(prefix) for prefix in prefixes)


def judge_path(
    path: Path, worktree: Path, part: str, prefixes: list[str]
) -> str | None:
    """The reason to block an edit of path by the agent of part; None to allow it."""
    shown = ", ".join(f"`{prefix}`" for prefix in prefixes) or "(אין)"
    if is_inside(path, worktree):
        relative = Path(os.path.relpath(path, worktree)).as_posix()
        if matches_part(relative, prefixes):
            return None
        return OUTSIDE_PART_REASON.format(path=path, part=part, prefixes=shown)
    return OTHER_WORKTREE_REASON.format(path=path, part=part, prefixes=shown)


def decide(event: dict) -> str | None:
    """The reason to block this tool call; None to let it through."""
    agent_id = event.get("agent_id")
    if event.get("tool_name") not in EDIT_TOOLS or not isinstance(agent_id, str):
        return None
    if not isinstance(event.get("tool_input"), dict):
        return None
    path = edit_target(event)
    if path is None or not agent_id:
        return None
    common = git_common_dir(existing_folder(path))
    if common is None:
        return None
    parts = load_parts(common)
    agent_git_dir = common / "worktrees" / f"agent-{agent_id}"
    part = read_text(agent_git_dir / REGISTRATION_FILE)
    if parts is None or not part:
        return None
    if is_inside(path, common):
        return GIT_DIR_REASON.format(path=path)
    if part not in parts:
        names = ", ".join(f"`{name}`" for name in parts) or "(אין)"
        return UNKNOWN_PART_REASON.format(part=part, parts=names)
    worktree = agent_worktree(agent_git_dir)
    if worktree is None:
        return None
    return judge_path(path, worktree, part, parts[part])


def main() -> int:
    """Read the tool call from stdin; return 2 to block it, 0 otherwise."""
    event = read_event(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    if event is None:
        return 0
    try:
        reason = decide(event)
    except (OSError, ValueError):
        return 0
    if reason is None:
        return 0
    sys.stderr.buffer.write(reason.encode("utf-8"))
    sys.stderr.flush()
    return 2


if __name__ == "__main__":
    sys.exit(main())
