"""PreToolUse hook: no repo edits and no branch switches in the main ~/.claude folder.

The main folder is the live skills and instructions every session loads, so code is
written only in a worktree (.claude/CLAUDE.md, rules/git.md; claude-config#62).

Wired in settings.json for Edit, Write, MultiEdit and NotebookEdit, and for the Bash and
PowerShell tools. Exit 0 with no output means no decision; exit 2 blocks the call, and
stderr is the reason Claude sees.

What may be written there on purpose (memory, plans, sessions, local settings) is
exactly what .gitignore keeps out of the repo, so `git check-ignore` is the allow-list.
Anything that goes wrong (no git, odd input) lets the call through: a guard that breaks
memory writes is worse than one that misses a case. Writes from shell commands
(`sed -i`, `>`) are not caught.
"""

import os
import subprocess
import sys
from pathlib import Path

from shell_commands import (
    edit_target,
    git_subcommand,
    read_event,
    shell_command,
    split_subcommands,
)

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
BRANCH_SWITCHES = ("checkout", "switch")
CHANGE_DIRECTORY = ("cd", "chdir", "pushd", "set-location", "sl")
# Tracked, yet Claude Code and the settings tools write it in place (claude-config#62).
ALLOWED_TRACKED = ("settings.json", "settings.local.json")
GIT_TIMEOUT_SECONDS = 5
EDIT_REASON = (
    "{path} נמצא בתיקייה הראשית של ~/.claude, שממנה כל הסשנים טוענים סקילים והנחיות.\n"
    "כותבים קוד רק ב-worktree: EnterWorktree, או `git worktree add`"
    " (.claude/CLAUDE.md, כללי עבודה).\n"
)
SWITCH_REASON = (
    "`git {subcommand}` בתיקייה הראשית של ~/.claude חסום: היא עותק משותף,"
    " ושינויים שלא נשמרו נגררים ל-branch הלא נכון.\n"
    "עובדים ב-worktree (rules/git.md, התיקייה המשותפת).\n"
)


def main_root() -> Path:
    """The main ~/.claude folder: CLAUDE_CONFIG_DIR when set, else ~/.claude."""
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured or Path.home() / ".claude").resolve()


def is_inside(path: Path, root: Path) -> bool:
    """True when path is root or below it, ignoring case where the OS does."""
    path_text = os.path.normcase(str(path))
    root_text = os.path.normcase(str(root))
    return path_text == root_text or path_text.startswith(root_text + os.sep)


def same_folder(first: Path, second: Path) -> bool:
    """True when both paths name the same folder, ignoring case where the OS does."""
    return os.path.normcase(str(first)) == os.path.normcase(str(second))


def run_git(folder: Path, *arguments: str) -> subprocess.CompletedProcess | None:
    """Run git in folder; None when git is missing or does not answer in time."""
    try:
        return subprocess.run(
            ["git", "-C", str(folder), *arguments],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def repo_toplevel(folder: Path) -> Path | None:
    """The top of the repo or worktree that holds folder; None outside any repo."""
    while not folder.is_dir() and folder != folder.parent:
        folder = folder.parent
    result = run_git(folder, "rev-parse", "--show-toplevel")
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).resolve()


def is_ignored(root: Path, path: Path) -> bool:
    """True when the main folder's .gitignore keeps path out of the repo."""
    relative = Path(os.path.relpath(path, root)).as_posix()
    result = run_git(root, "check-ignore", "-q", "--", relative)
    return result is None or result.returncode == 0


def blocks_edit(path: Path, root: Path) -> bool:
    """True when path is a repo file of the main folder itself, not of a worktree."""
    if not is_inside(path, root):
        return False
    toplevel = repo_toplevel(path.parent)
    if toplevel is None or not same_folder(toplevel, root):
        return False
    if same_folder(path.parent, root) and path.name.lower() in ALLOWED_TRACKED:
        return False
    return not is_ignored(root, path)


def change_folder(current: Path, arguments: list[str]) -> Path:
    """Where `cd <arguments>` lands, starting from current."""
    targets = [argument for argument in arguments if not argument.startswith("-")]
    if not targets:
        return Path.home()
    return (current / os.path.expandvars(os.path.expanduser(targets[0]))).resolve()


def git_folder(current: Path, options: list[str]) -> Path:
    """The folder git works in: current, moved by each `-C <path>` in order."""
    folder = current
    for index, option in enumerate(options[:-1]):
        if option == "-C":
            value = os.path.expandvars(os.path.expanduser(options[index + 1]))
            folder = (folder / value).resolve()
    return folder


def blocked_switch(command: str, cwd: Path, root: Path) -> str | None:
    """The `git checkout` or `git switch` that would run in the main folder, if any."""
    current = cwd
    for words in split_subcommands(command):
        if words[0].lower() in CHANGE_DIRECTORY:
            current = change_folder(current, words[1:])
            continue
        parts = git_subcommand(words)
        if parts is None or parts[1] not in BRANCH_SWITCHES:
            continue
        toplevel = repo_toplevel(git_folder(current, parts[0]))
        if toplevel is not None and same_folder(toplevel, root):
            return parts[1]
    return None


def decide(event: dict) -> str | None:
    """The reason to block this tool call; None to let it through."""
    root = main_root()
    if event.get("tool_name") in EDIT_TOOLS:
        path = edit_target(event)
        if path is not None and blocks_edit(path, root):
            return EDIT_REASON.format(path=path)
        return None
    command = shell_command(event)
    if command is None or not any(word in command for word in BRANCH_SWITCHES):
        return None
    subcommand = blocked_switch(command, Path(event.get("cwd") or os.getcwd()), root)
    return SWITCH_REASON.format(subcommand=subcommand) if subcommand else None


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
