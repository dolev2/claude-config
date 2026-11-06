"""Shared by the hooks: reading the tool call from stdin, the file an edit writes, and
splitting shell commands.

Imported by hooks that sit next to it in hooks/; Python puts the script's own folder
first on sys.path, so a plain `import shell_commands` finds it.
"""

import json
import os
import re
import shlex
from pathlib import Path, PurePath

SHELL_TOOLS = ("Bash", "PowerShell")
SEPARATOR_CHARS = ";&|\n"
# Run their argument as the command; `timeout` also takes a duration first.
WRAPPERS = {"command", "builtin", "nohup", "nice", "time", "stdbuf", "sudo"}
# git options before the subcommand whose value is the next argument.
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
# `<<EOF`, `<<-'EOF'`, `<< "EOF"`; not the `<<<` here-string, which has no body.
HEREDOC_START = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)(\w+)\2")
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
    words = strip_prefixes(words)
    if len(words) < 2 or PurePath(words[0]).name.lower() not in ("gh", "gh.exe"):
        return None
    return words[2:] if words[1] == "api" else None


def native_path(text: str, is_windows: bool = os.name == "nt") -> str:
    """The path as the OS reads it: on Windows, Git Bash's `/c/Users` is `C:/Users`.

    Without this, Python reads `/c/Users` as `C:\\c\\Users`, which does not exist.
    """
    if not is_windows:
        return text
    return MSYS_DRIVE.sub(lambda match: f"{match.group(1).upper()}:", text)


def strip_heredocs(command: str) -> str:
    """The command without heredoc bodies, which are text and not commands."""
    lines = command.split("\n")
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        kept.append(line)
        index += 1
        for strip_tabs, _quote, delimiter in HEREDOC_START.findall(line):
            while index < len(lines):
                body_line = lines[index].lstrip("\t") if strip_tabs else lines[index]
                index += 1
                if body_line.rstrip("\r") == delimiter:
                    break
    return "\n".join(kept)


def split_subcommands(command: str) -> list[list[str]]:
    """The command's words, one list per subcommand between `&&`, `;`, `|` or a newline.

    Quotes are respected, so `git commit -m "a; git push -f"` stays one subcommand, and
    heredoc bodies are skipped. Text shlex cannot parse (an open quote) falls back to
    splitting on whitespace.
    """
    command = strip_heredocs(command)
    lexer = shlex.shlex(command, posix=True, punctuation_chars=SEPARATOR_CHARS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    subcommands: list[list[str]] = [[]]
    for token in tokens:
        if token and all(char in SEPARATOR_CHARS for char in token):
            subcommands.append([])
        else:
            subcommands[-1].append(token)
    return [words for words in subcommands if words]


def strip_prefixes(words: list[str]) -> list[str]:
    """The words without leading `VAR=value` assignments and wrappers (`timeout 30`)."""
    index = 0
    while index < len(words):
        word = words[index]
        if word in WRAPPERS or ("=" in word and word.split("=")[0].isidentifier()):
            index += 1
        elif word == "timeout":
            index += 2
        else:
            break
    return words[index:]


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
