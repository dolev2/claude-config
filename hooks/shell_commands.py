"""Shared by the hooks: reading the tool call from stdin, the file an edit writes, and
the gh and git subcommand of a command. Splitting the shell line is in shell_split.py.

Imported by hooks that sit next to it in hooks/; Python puts the script's own folder
first on sys.path, so a plain `import shell_commands` finds it.
"""

import json
import os
import re
from pathlib import Path, PurePath

from shell_split import strip_prefixes

SHELL_TOOLS = ("Bash", "PowerShell")
# git options before the subcommand whose value is the next argument.
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
# Git Bash writes C:\Users as /c/Users.
MSYS_DRIVE = re.compile(r"^/([a-zA-Z])(?=/|$)")
# GitHub MCP tools that merge a PR or turn on its auto-merge, under any server name.
MCP_MERGE_TOOLS = ("__merge_pull_request", "__enable_pr_auto_merge")
# `pulls/5/merge`, `pulls/$PR/merge`, `/repos/a/b/pulls/5/merge`, a URL, with a query.
MERGE_ENDPOINT = re.compile(r"(^|/)pulls/[^/\s]+/merge/?(\?.*)?$")


def read_event(raw: str) -> dict | None:
    """The tool call Claude Code sent as JSON; None when it is not a JSON object."""
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def shell_command(event: dict) -> str | None:
    """The command of a Bash or PowerShell tool call; None for anything else."""
    if event.get("tool_name") not in SHELL_TOOLS:
        return None
    command = (event.get("tool_input") or {}).get("command")
    return command if isinstance(command, str) else None


def edit_target(event: dict) -> Path | None:
    """The file an edit tool call writes, made absolute against the session folder."""
    tool_input = event.get("tool_input") or {}
    target = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(target, str) or not target:
        return None
    path = Path(os.path.expanduser(target))
    if not path.is_absolute():
        path = Path(event.get("cwd") or os.getcwd()) / path
    return path.resolve()


def is_mcp_merge(event: dict) -> bool:
    """True for an MCP tool that merges a PR or turns on its auto-merge."""
    name = event.get("tool_name")
    return (
        isinstance(name, str)
        and name.startswith("mcp__")
        and name.endswith(MCP_MERGE_TOOLS)
    )


def gh_api_arguments(words: list[str]) -> list[str] | None:
    """The arguments after `gh api`; None when the command is not `gh api`."""
    arguments = gh_subcommand(words)
    if not arguments or arguments[0] != "api":
        return None
    return arguments[1:]


def native_path(text: str, is_windows: bool = os.name == "nt") -> str:
    """The path as the OS reads it: on Windows, Git Bash's `/c/Users` is `C:/Users`.

    Without this, Python reads `/c/Users` as `C:\\c\\Users`, which does not exist.
    """
    if not is_windows:
        return text
    return MSYS_DRIVE.sub(lambda match: f"{match.group(1).upper()}:", text)


def gh_subcommand(words: list[str]) -> list[str] | None:
    """The words after `gh`, without `-R`/`--repo` and its value; None when not gh.

    gh takes `-R` anywhere after the command group: `gh -R a/b pr merge`, `gh pr -R a/b
    merge`.
    """
    words = strip_prefixes(words)
    if not words or PurePath(words[0]).name.lower() not in ("gh", "gh.exe"):
        return None
    kept: list[str] = []
    skip_value = False
    for word in words[1:]:
        if skip_value:
            skip_value = False
        elif word in ("-R", "--repo"):
            skip_value = True
        elif not word.startswith(("-R", "--repo=")):
            kept.append(word)
    return kept


def git_subcommand(words: list[str]) -> tuple[list[str], str, list[str]] | None:
    """Split `git <options> <subcommand> <arguments>`; None when it is not git.

    Returns the options before the subcommand, the subcommand, and its arguments.
    """
    words = strip_prefixes(words)
    if not words or PurePath(words[0]).name.lower() not in ("git", "git.exe"):
        return None
    index = 1
    while index < len(words) and words[index].startswith("-"):
        index += 2 if words[index] in GIT_OPTIONS_WITH_VALUE else 1
    if index >= len(words):
        return None
    return words[1:index], words[index], words[index + 1 :]
