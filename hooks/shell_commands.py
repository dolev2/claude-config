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
# `(`, `)` and the backtick open or close a subshell; each one also ends a subcommand.
SEPARATOR_CHARS = ";&|\n()`"
# Words a shell reads before the command itself: `if git push -f; then ...`.
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}"}
# Run their argument as the command, after their own options. The value is the options
# that take the next word as their value; `timeout` also takes a duration after them.
WRAPPERS = {
    "builtin": set(),
    "command": set(),
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "exec": {"-a"},
    "nice": {"-n", "--adjustment"},
    "nohup": set(),
    "stdbuf": {"-i", "-o", "-e"},
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T"},
    "time": {"-f", "-o", "--format", "--output"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a", "--arg-file"},
}
# Shells whose `-c <text>` runs the text as a command; `eval` does the same.
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# How deep `bash -c "sh -c '...'"` is unwrapped; deeper text is not read.
MAX_NESTING = 3
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


def command_substitutions(command: str) -> list[str]:
    """The text inside each `$(...)` and backtick pair that is not in single quotes.

    Inside double quotes these still run, and shlex would keep them in one word.
    """
    found: list[str] = []
    quote = ""
    index = 0
    while index < len(command):
        char = command[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if quote == "'":
            quote = "" if char == "'" else quote
        elif char == "'" and not quote:
            quote = "'"
        elif char == '"':
            quote = "" if quote == '"' else '"'
        elif command.startswith("$(", index):
            end = closing_parenthesis(command, index + 2)
            found.append(command[index + 2 : end])
            index = end
        elif char == "`":
            end = command.find("`", index + 1)
            end = len(command) if end == -1 else end
            found.append(command[index + 1 : end])
            index = end
        index += 1
    return found


def closing_parenthesis(command: str, start: int) -> int:
    """The index of the `)` that closes the `(` just before start, or the text's end."""
    depth = 1
    for index in range(start, len(command)):
        if command[index] == "(":
            depth += 1
        elif command[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return len(command)


def split_words(command: str) -> list[list[str]]:
    """The words of each subcommand between `&&`, `;`, `|`, `(`, `)` or a newline."""
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


def nested_command(words: list[str]) -> str | None:
    """The text that `sh -c '<text>'` or `eval <text>` runs; None for anything else."""
    words = strip_prefixes(words)
    if not words:
        return None
    name = PurePath(words[0]).name.lower()
    if name == "eval":
        return " ".join(words[1:])
    if name not in SHELLS:
        return None
    for index, word in enumerate(words[1:-1], start=1):
        if not word.startswith("-") or word.startswith("--"):
            return None
        if "c" in word:
            return words[index + 1]
    return None


def split_subcommands(command: str, depth: int = 0) -> list[list[str]]:
    """The command's words, one list per subcommand it runs.

    Subcommands are split at `&&`, `;`, `|`, `(`, `)` and newlines; the text of
    `$(...)`, backticks, `sh -c` and `eval` is split again as commands of its own.
    Quotes are respected, so `git commit -m "a; git push -f"` stays one subcommand, and
    heredoc bodies are skipped. Text shlex cannot parse (an open quote) falls back to
    splitting on whitespace.
    """
    command = strip_heredocs(command)
    subcommands = split_words(command)
    if depth >= MAX_NESTING:
        return subcommands
    inner = command_substitutions(command)
    inner += [text for words in subcommands if (text := nested_command(words))]
    for text in inner:
        subcommands += split_subcommands(text, depth + 1)
    return subcommands


def is_assignment(word: str) -> bool:
    """True for a `NAME=value` word."""
    return "=" in word and word.split("=")[0].isidentifier()


def skip_options(words: list[str], index: int, with_value: set[str]) -> int:
    """The index of the first word after a wrapper's options, from index on."""
    while index < len(words) and words[index].startswith("-"):
        word = words[index]
        index += 1
        if word == "--":
            break
        if word in with_value:
            index += 1
    return index


def parse_prefixes(words: list[str]) -> tuple[dict[str, str], list[str]]:
    """The `VAR=value` assignments before the command, and the command's own words.

    Shell keywords (`if`, `then`, `{`) and wrappers with their options (`env -i`,
    `timeout -s KILL 30`, `sudo -u root`) are dropped on the way.
    """
    assignments: dict[str, str] = {}
    index = 0
    while index < len(words):
        word = words[index]
        name = PurePath(word).name.lower()
        if word in KEYWORDS:
            index += 1
        elif is_assignment(word):
            key, value = word.split("=", 1)
            assignments[key] = value
            index += 1
        elif name in WRAPPERS:
            index = skip_options(words, index + 1, WRAPPERS[name])
            index += 1 if name == "timeout" else 0
        else:
            break
    return assignments, words[index:]


def strip_prefixes(words: list[str]) -> list[str]:
    """The words without leading keywords, `VAR=value` assignments and wrappers."""
    return parse_prefixes(words)[1]


def gh_subcommand(words: list[str]) -> list[str] | None:
    """The words after `gh` and its `-R`/`--repo` option; None when it is not gh."""
    words = strip_prefixes(words)
    if not words or PurePath(words[0]).name.lower() not in ("gh", "gh.exe"):
        return None
    index = 1
    while index < len(words) and words[index].startswith(("-R", "--repo")):
        index += 2 if words[index] in ("-R", "--repo") else 1
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
