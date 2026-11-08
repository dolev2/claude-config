"""PreToolUse hook: no repo edits and no work-losing git commands in the main ~/.claude.

The main folder is the live skills and instructions every session loads, so code is
written only in a worktree (.claude/CLAUDE.md, rules/git.md; claude-config#62).

Wired in settings.json for Edit, Write, MultiEdit and NotebookEdit, and for the Bash and
PowerShell tools. Exit 0 with no output means no decision; exit 2 blocks the call, and
stderr is the reason Claude sees.

What may be written there on purpose (memory, plans, sessions, local settings) is
exactly what .gitignore keeps out of the repo, so `git check-ignore` is the allow-list.
The exception is what .gitignore hides but every session still runs or loads: `.git/`,
Python's bytecode cache, the skills the cloud service syncs, agents, commands, plugins
and output styles (LIVE_IGNORED; claude-config#163).

The git commands blocked there are the ones that switch the branch or throw away work
that is not committed: checkout, switch, `reset --hard`, restore of the working tree,
stash, writing symbolic-ref, `clean -f`. The folder is found from `cd`, `-C`,
`--git-dir`, `--work-tree`, and `GIT_DIR=` / `GIT_WORK_TREE=` before the command.

Anything that goes wrong (no git, odd input, no Python) lets the call through: a guard
that breaks memory writes is worse than one that misses a case. Writes from shell
commands (`sed -i`, `>`) are not caught.
"""

import os
import subprocess
import sys
from pathlib import Path

from shell_commands import (
    edit_target,
    git_subcommand,
    native_path,
    read_event,
    shell_command,
)
from shell_split import parse_prefixes, split_subcommands

EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
# Git commands that switch the branch or can throw away uncommitted work.
GUARDED_SUBCOMMANDS = (
    "checkout",
    "switch",
    "reset",
    "restore",
    "stash",
    "symbolic-ref",
    "clean",
)
# Ignored by .gitignore, yet run or loaded by every session: first folder, or any part.
LIVE_IGNORED_TOP = ("skills/synced", "skills/session-start-hook", "agents", "commands")
LIVE_IGNORED_TOP += ("plugins", "output-styles")
LIVE_IGNORED_PARTS = ("__pycache__",)
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
    " ושינויים שלא נשמרו נגררים ל-branch הלא נכון או נמחקים.\n"
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
            encoding="utf-8",
            errors="replace",
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


def is_live_ignored(relative: str) -> bool:
    """True for a path .gitignore hides that sessions still run or load."""
    parts = relative.lower().split("/")
    if any(part in LIVE_IGNORED_PARTS for part in parts) or relative.endswith(".pyc"):
        return True
    return any(f"{relative.lower()}/".startswith(f"{top}/") for top in LIVE_IGNORED_TOP)


def blocks_edit(path: Path, root: Path) -> bool:
    """True when path is a repo file of the main folder itself, not of a worktree."""
    if not is_inside(path, root):
        return False
    relative = Path(os.path.relpath(path, root)).as_posix()
    if relative.split("/")[0].lower() == ".git":
        return True
    toplevel = repo_toplevel(path.parent)
    if toplevel is None or not same_folder(toplevel, root):
        return False
    if same_folder(path.parent, root) and path.name.lower() in ALLOWED_TRACKED:
        return False
    return is_live_ignored(relative) or not is_ignored(root, path)


def expand(path_text: str) -> str:
    """A path from a shell command with `~`, `$VAR` and Git Bash drives resolved."""
    return native_path(os.path.expandvars(os.path.expanduser(path_text)))


def change_folder(current: Path, arguments: list[str]) -> Path:
    """Where `cd <arguments>` lands, starting from current."""
    targets = [argument for argument in arguments if not argument.startswith("-")]
    if not targets:
        return Path.home()
    return (current / expand(targets[0])).resolve()


def option_values(options: list[str], name: str) -> list[str]:
    """The values of `name <value>` and `name=<value>` among git's options, in order."""
    values = []
    for index, option in enumerate(options):
        if option == name and index + 1 < len(options):
            values.append(options[index + 1])
        elif option.startswith(f"{name}="):
            values.append(option.split("=", 1)[1])
    return values


def git_folders(
    current: Path, options: list[str], assignments: dict[str, str]
) -> list[Path]:
    """The folders git works in: current, moved by `-C`, then the work tree or git dir.

    `--git-dir` (or `GIT_DIR=`) names the `.git` folder, so its parent is the repo. With
    no work tree named, git writes the files in the current folder: both count.
    """
    folder = current
    for path in option_values(options, "-C"):
        folder = (folder / expand(path)).resolve()
    work_trees = option_values(options, "--work-tree")
    git_dirs = option_values(options, "--git-dir")
    work_tree = work_trees[-1] if work_trees else assignments.get("GIT_WORK_TREE")
    git_dir = git_dirs[-1] if git_dirs else assignments.get("GIT_DIR")
    if work_tree:
        return [(folder / expand(work_tree)).resolve()]
    if git_dir:
        return [(folder / expand(git_dir)).resolve().parent, folder]
    return [folder]


def is_guarded(subcommand: str, arguments: list[str]) -> bool:
    """True when this git command switches the branch or can lose uncommitted work."""
    flags = [argument for argument in arguments if argument.startswith("-")]
    if subcommand in ("checkout", "switch"):
        return True
    if subcommand == "reset":
        return any(flag in ("--hard", "--merge", "--keep") for flag in flags)
    if subcommand == "restore":
        staged_only = any(flag in ("--staged", "-S") for flag in flags)
        return not staged_only or any(flag in ("--worktree", "-W") for flag in flags)
    if subcommand == "stash":
        return not arguments or arguments[0] not in ("list", "show")
    if subcommand == "symbolic-ref":
        deletes = any(flag in ("-d", "--delete") for flag in flags)
        return deletes or len(arguments) - len(flags) >= 2
    if subcommand == "clean":
        short = [flag for flag in flags if not flag.startswith("--")]
        return "--force" in flags or any("f" in flag for flag in short)
    return False


def blocked_switch(command: str, cwd: Path, root: Path) -> str | None:
    """The guarded git command that would run in the main folder, if any.

    A `cd` or `export` inside `(...)` is read as if it stayed in effect after it. That
    can go either way: `(cd /tmp); git checkout x` run in the main folder passes.
    """
    current = cwd
    exported: dict[str, str] = {}
    for words in split_subcommands(command):
        assignments, command_words = parse_prefixes(words)
        name = command_words[0].lower() if command_words else ""
        if name in CHANGE_DIRECTORY:
            current = change_folder(current, command_words[1:])
            continue
        if name == "export":
            exported.update(parse_prefixes(command_words[1:])[0])
            continue
        parts = git_subcommand(words)
        if parts is None or not is_guarded(parts[1], parts[2]):
            continue
        folders = git_folders(current, parts[0], {**exported, **assignments})
        for folder in folders:
            toplevel = repo_toplevel(folder)
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
    if command is None or not any(word in command for word in GUARDED_SUBCOMMANDS):
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
