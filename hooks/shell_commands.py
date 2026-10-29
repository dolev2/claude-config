"""Shared by the hooks: reading the tool call from stdin and splitting shell commands.

Imported by hooks that sit next to it in hooks/; Python puts the script's own folder
first on sys.path, so a plain `import shell_commands` finds it.
"""

import json
import shlex
from pathlib import PurePath

SHELL_TOOLS = ("Bash", "PowerShell")
SEPARATOR_CHARS = ";&|\n"
# Run their argument as the command; `timeout` also takes a duration first.
WRAPPERS = {"command", "builtin", "nohup", "nice", "time", "stdbuf", "sudo"}
# git options before the subcommand whose value is the next argument.
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


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


def split_subcommands(command: str) -> list[list[str]]:
    """The command's words, one list per subcommand between `&&`, `;`, `|` or a newline.

    Quotes are respected, so `git commit -m "a; git push -f"` stays one subcommand.
    Text shlex cannot parse (an open quote) falls back to splitting on whitespace.
    """
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
