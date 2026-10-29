"""PreToolUse hook: blocks `git push --force` and lets `--force-with-lease` through.

Wired in settings.json for the Bash and PowerShell tools (claude-config#61), run by
python3 or python, whichever exists, from $HOME/.claude/hooks/.

Claude Code sends the tool call as JSON on stdin. Exit 0 with no output means no
decision, and the normal permission rules decide. Exit 2 blocks the call, and stderr is
the reason Claude sees.

A deny rule cannot do this: it matches text, so `*--force*` would also block
`--force-with-lease`, and it misses `-fu` and a `+main` refspec. This is a guard against
mistakes, not a security boundary: `sh -c 'git push -f'` is not caught.
"""

import json
import shlex
import sys
from pathlib import PurePath

SHELL_TOOLS = ("Bash", "PowerShell")
SEPARATOR_CHARS = ";&|\n"
# Run their argument as the command; `timeout` also takes a duration first.
WRAPPERS = {"command", "builtin", "nohup", "nice", "time", "stdbuf", "sudo"}
# git options before the subcommand whose value is the next argument.
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
REASON = (
    "דחיפה בכוח חסומה: `--force`, `-f` או refspec עם `+` דורסים בשקט commits"
    " שמישהו אחר דחף בינתיים.\n"
    "משתמשים ב-`git push --force-with-lease` (rules/git.md, נהלי git).\n"
)


def read_command(raw: str) -> str | None:
    """The shell command of a Bash or PowerShell tool call; None for anything else."""
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(event, dict) or event.get("tool_name") not in SHELL_TOOLS:
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


def push_arguments(words: list[str]) -> list[str] | None:
    """The arguments after `git ... push`; None when the subcommand is not a push."""
    words = strip_prefixes(words)
    if not words or PurePath(words[0]).name.lower() not in ("git", "git.exe"):
        return None
    index = 1
    while index < len(words) and words[index].startswith("-"):
        index += 2 if words[index] in GIT_OPTIONS_WITH_VALUE else 1
    if index >= len(words) or words[index] != "push":
        return None
    return words[index + 1 :]


def is_force_push(arguments: list[str]) -> bool:
    """True when the push arguments overwrite the remote without a lease."""
    only_refspecs = False
    skip_value = False
    for argument in arguments:
        if skip_value:
            skip_value = False
        elif only_refspecs or not argument.startswith("-") or argument == "-":
            if argument.startswith("+"):
                return True
        elif argument == "--":
            only_refspecs = True
        elif argument == "--force":
            return True
        elif argument.startswith("--"):
            continue
        else:
            # Short flags can be grouped (`-fu`); what follows `-o` is its value.
            flags, has_option_value, inline_value = argument[1:].partition("o")
            if "f" in flags:
                return True
            skip_value = bool(has_option_value) and not inline_value
    return False


def main() -> int:
    """Read the tool call from stdin; return 2 to block a force push, 0 otherwise."""
    command = read_command(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    if command is None or "push" not in command:
        return 0
    for words in split_subcommands(command):
        arguments = push_arguments(words)
        if arguments is not None and is_force_push(arguments):
            sys.stderr.buffer.write(REASON.encode("utf-8"))
            sys.stderr.flush()
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
