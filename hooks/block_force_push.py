"""PreToolUse hook: blocks `git push --force` and lets `--force-with-lease` through.

Also blocked: `push --mirror`, which overwrites every ref, and `git send-pack --force`
or a `+` refspec there (claude-config#163).

Wired in settings.json for the Bash and PowerShell tools (claude-config#61), run by
python3 or python, whichever exists, from $HOME/.claude/hooks/.

Claude Code sends the tool call as JSON on stdin. Exit 0 with no output means no
decision, and the normal permission rules decide. Exit 2 blocks the call, and stderr is
the reason Claude sees.

A deny rule cannot do this: it matches text, so `*--force*` would also block
`--force-with-lease`, and it misses `-fu` and a `+main` refspec.

This is a guard against mistakes, not a security boundary; on the default branch the
ruleset is (claude-config#162). Wrappers a command is often written in (`env`, `(...)`,
`if`, `$(...)`, `bash -c`) are read through shell_commands.py. Not read, by decision
(claude-config#163): a push hidden in config set on the command line, `git -c
alias.p='push -f' p` or `git -c remote.origin.push=+HEAD:main push`; nobody writes those
by accident. Input that is not a JSON object with a string command passes (Claude Code
never sends it), and so does a call whose hook cannot start for lack of Python (exit
127, shown as a hook error; README).
"""

import sys

from shell_commands import git_subcommand, read_event, shell_command
from shell_split import split_subcommands

REASON = (
    "דחיפה בכוח חסומה: `--force`, `-f` או refspec עם `+` דורסים בשקט commits"
    " שמישהו אחר דחף בינתיים.\n"
    "משתמשים ב-`git push --force-with-lease` (rules/git.md, נהלי git).\n"
)


def read_command(raw: str) -> str | None:
    """The shell command of a Bash or PowerShell tool call; None for anything else."""
    event = read_event(raw)
    return shell_command(event) if event is not None else None


def push_arguments(words: list[str]) -> list[str] | None:
    """The arguments after `git ... push` or `send-pack`; None for any other command."""
    parts = git_subcommand(words)
    if parts is None or parts[1] not in ("push", "send-pack"):
        return None
    return parts[2]


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
        elif argument in ("--force", "--mirror"):
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
    if command is None or not any(word in command for word in ("push", "send-pack")):
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
