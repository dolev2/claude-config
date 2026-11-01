"""PreToolUse hook: blocks `gh pr merge` with a hand-written `--subject`.

Wired in settings.json for the Bash and PowerShell tools (claude-config#87), run by
python3 or python, whichever exists, from $HOME/.claude/hooks/.

Claude Code sends the tool call as JSON on stdin. Exit 0 with no output means no
decision, and the normal permission rules decide. Exit 2 blocks the call, and stderr is
the reason Claude sees.

A merge commit's title lands on the default branch for good. Without `--subject`, GitHub
takes it from the PR title (the repo's `squash_merge_commit_title` is `PR_TITLE`, set by
dev-setup), so a wrong title is fixed on the PR with `gh pr edit --title`. A deny rule
cannot do this: `*--subject*` misses `-t` and grouped flags like `-st`. This is a guard
against mistakes, not a security boundary: `gh api` and `sh -c` are not caught.
"""

import sys
from pathlib import PurePath

from shell_commands import read_event, shell_command, split_subcommands, strip_prefixes

REASON = (
    "מיזוג עם `--subject` או `-t` חסום: כותרת ה-commit נלקחת מכותרת ה-PR.\n"
    'כותרת שגויה מתקנים קודם ב-`gh pr edit <N> --title "<title>"`, ואז'
    " `gh pr merge <N> --squash` בלי `--subject` (claude-config#87).\n"
)

# Shorthand flags of `gh pr merge` that take a value; letters after them are the value.
SHORT_FLAGS_WITH_VALUE = set("AbFRt")
LONG_FLAGS_WITH_VALUE = {
    "--author-email",
    "--body",
    "--body-file",
    "--match-head-commit",
    "--repo",
}


def read_command(raw: str) -> str | None:
    """The shell command of a Bash or PowerShell tool call; None for anything else."""
    event = read_event(raw)
    return shell_command(event) if event is not None else None


def merge_arguments(words: list[str]) -> list[str] | None:
    """The arguments after `gh pr merge`; None when the command is not a PR merge."""
    words = strip_prefixes(words)
    if len(words) < 3 or PurePath(words[0]).name.lower() not in ("gh", "gh.exe"):
        return None
    if words[1:3] != ["pr", "merge"]:
        return None
    return words[3:]


def sets_subject(arguments: list[str]) -> bool:
    """True when the merge arguments set the commit subject."""
    skip_value = False
    for argument in arguments:
        if skip_value:
            skip_value = False
        elif argument == "--":
            return False
        elif argument.startswith("--"):
            name = argument.split("=")[0]
            if name == "--subject":
                return True
            skip_value = name in LONG_FLAGS_WITH_VALUE and "=" not in argument
        elif argument.startswith("-") and argument != "-":
            for index, letter in enumerate(argument[1:]):
                if letter == "t":
                    return True
                if letter in SHORT_FLAGS_WITH_VALUE:
                    skip_value = index == len(argument) - 2
                    break
    return False


def main() -> int:
    """Read the tool call from stdin; return 2 to block a merge subject, 0 otherwise."""
    command = read_command(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    if command is None or "merge" not in command:
        return 0
    for words in split_subcommands(command):
        arguments = merge_arguments(words)
        if arguments is not None and sets_subject(arguments):
            sys.stderr.buffer.write(REASON.encode("utf-8"))
            sys.stderr.flush()
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
