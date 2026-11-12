"""Shared by the hooks: reading the tool call from stdin, the file an edit writes, and
the gh and git subcommand of a command. Splitting the shell line is in shell_split.py.

Imported by hooks that sit next to it in hooks/; Python puts the script's own folder
first on sys.path, so a plain `import shell_commands` finds it.
"""

import json
import os
import re
from pathlib import Path, PurePath

from shell_split import split_subcommands, strip_prefixes

SHELL_TOOLS = ("Bash", "PowerShell")
# git options before the subcommand whose value is the next argument.
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
# Git Bash writes C:\Users as /c/Users.
MSYS_DRIVE = re.compile(r"^/([a-zA-Z])(?=/|$)")
# GitHub MCP tools that merge a PR or turn on its auto-merge, under any server name.
MCP_MERGE_TOOLS = ("__merge_pull_request", "__enable_pr_auto_merge")
# The one that merges now; auto-merge happens later, without Claude.
MCP_PR_MERGE_TOOLS = ("__merge_pull_request",)
# `pulls/5/merge`, `pulls/$PR/merge`, `/repos/a/b/pulls/5/merge`, a URL, with a query.
MERGE_ENDPOINT = re.compile(r"(^|/)pulls/[^/\s]+/merge/?(\?.*)?$")
FIELD_FLAGS = ("-f", "-F", "--field", "--raw-field", "--input")
# `gh api` options whose value is the next word, so it is not the endpoint.
API_OPTIONS_WITH_VALUE = {
    "-X", "--method", "-f", "-F", "--field", "--raw-field", "-H", "--header",
    "--input", "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p",
    "--preview",
}  # fmt: skip
# Options of `gh pr merge` and `gh api` whose value is the next word, so a `-R` there is
# that value and not the repo (claude-config#329). gh reads the next word as the value
# even when it starts with `-`.
GH_LONG_OPTIONS_WITH_VALUE = API_OPTIONS_WITH_VALUE | {
    "--body", "--body-file", "--subject", "--author-email", "--match-head-commit",
}  # fmt: skip
# Their one-letter forms; in a group like `-sb`, the letters after one are its value.
GH_SHORT_OPTIONS_WITH_VALUE = set("AbFtXfHqp")


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


def is_mcp_merge(event: dict, tools: tuple[str, ...] = MCP_MERGE_TOOLS) -> bool:
    """True for an MCP tool that merges a PR or turns on its auto-merge.

    `tools=MCP_PR_MERGE_TOOLS` leaves out auto-merge: only a merge that happens now.
    """
    name = event.get("tool_name")
    return isinstance(name, str) and name.startswith("mcp__") and name.endswith(tools)


def http_method(arguments: list[str]) -> str | None:
    """The method `-X`, `--method`, `-XPUT` or `--method=PUT` sets, or None."""
    for index, argument in enumerate(arguments):
        if argument in ("-X", "--method"):
            return arguments[index + 1].upper() if index + 1 < len(arguments) else None
        if argument.startswith("--method="):
            return argument.split("=", 1)[1].upper()
        if argument.startswith("-X") and len(argument) > 2:
            return argument[2:].upper()
    return None


def effective_method(arguments: list[str]) -> str:
    """The method `gh api` sends: the one set, else POST with fields, else GET."""
    method = http_method(arguments)
    if method is not None:
        return method
    has_fields = any(argument.startswith(FIELD_FLAGS) for argument in arguments)
    return "POST" if has_fields else "GET"


def endpoint(arguments: list[str]) -> str | None:
    """The path `gh api` calls: its first argument that is not an option or a value."""
    skip_value = False
    for argument in arguments:
        if skip_value:
            skip_value = False
        elif argument in API_OPTIONS_WITH_VALUE:
            skip_value = True
        elif not argument.startswith("-"):
            return argument
    return None


def is_rest_pr_merge(arguments: list[str]) -> bool:
    """True for the `gh api` arguments of a REST PR merge: PUT pulls/<N>/merge."""
    path = endpoint(arguments) or ""
    return effective_method(arguments) == "PUT" and bool(MERGE_ENDPOINT.search(path))


def is_gh_pr_merge(words: list[str], include_auto: bool = True) -> bool:
    """True for `gh [-R repo] pr merge`; with include_auto=False, not for `--auto`."""
    arguments = gh_subcommand(words) or []
    if arguments[:2] != ["pr", "merge"]:
        return False
    return include_auto or "--auto" not in arguments[2:]


def is_shell_pr_merge(command: str) -> bool:
    """True when a subcommand merges a PR now: `gh pr merge`, or a REST PUT.

    Leaves out `gh pr merge --auto`, which merges later, and what only may merge (a
    `gh alias`, GraphQL from a file); the approval window in ask_before_merge.py asks
    about all of those too.
    """
    for words in split_subcommands(command):
        if is_gh_pr_merge(words, include_auto=False):
            return True
        arguments = gh_api_arguments(words)
        if arguments is not None and is_rest_pr_merge(arguments):
            return True
    return False


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
    merge`. A `-R` that is the value of another option (`--body -R`) is kept.
    """
    words = strip_prefixes(words)
    if not words or PurePath(words[0]).name.lower() not in ("gh", "gh.exe"):
        return None
    kept: list[str] = []
    skip_repo = keep_value = False
    for word in words[1:]:
        if keep_value:
            keep_value = False
            kept.append(word)
        elif skip_repo:
            skip_repo = False
        elif word in ("-R", "--repo"):
            skip_repo = True
        elif not word.startswith(("-R", "--repo=")):
            kept.append(word)
            keep_value = takes_next_word(word)
    return kept


def takes_next_word(word: str) -> bool:
    """True when the gh option `word` takes the next word as its value.

    `--body`, `-b` and `-sb` do; `--body=x`, `-bx` and `-sbx` do not.
    """
    if word.startswith("--"):
        return word in GH_LONG_OPTIONS_WITH_VALUE
    if not word.startswith("-") or word == "-":
        return False
    for index, letter in enumerate(word[1:]):
        if letter in GH_SHORT_OPTIONS_WITH_VALUE:
            return index == len(word) - 2
    return False


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
