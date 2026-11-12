"""PreToolUse hook: blocks a PR merge with a hand-written commit title.

Wired in settings.json for the Bash and PowerShell tools (claude-config#87) and for the
GitHub MCP merge tools (claude-config#135), run by python3 or python, whichever exists,
from $HOME/.claude/hooks/. Caught: `gh pr merge --subject` or `-t`, `commit_title` in an
MCP merge tool, and `-f`/`-F commit_title=` in `gh api ... pulls/<N>/merge`.

Claude Code sends the tool call as JSON on stdin. Exit 0 with no output means no
decision, and the normal permission rules decide. Exit 2 blocks the call, and stderr is
the reason Claude sees.

A merge commit's title lands on the default branch for good. Without `--subject`, GitHub
takes it from the PR title (the repo's `squash_merge_commit_title` is `PR_TITLE`, set by
dev-setup), so a wrong title is fixed on the PR with `gh pr edit --title`. A deny rule
cannot do this: `*--subject*` misses `-t` and grouped flags like `-st`. This is a guard
against mistakes, not a security boundary. `-R`/`--repo` anywhere after `gh`, and
`sh -c` or `bash -c` wrappers, are read; `--input`, a gh alias and GraphQL are not.
"""

import sys

from shell_commands import (
    MERGE_ENDPOINT,
    gh_api_arguments,
    gh_subcommand,
    is_mcp_merge,
    read_event,
    shell_command,
)
from shell_split import split_subcommands

REASON = (
    "מיזוג עם `--subject` או `-t` חסום: כותרת ה-commit נלקחת מכותרת ה-PR.\n"
    'כותרת שגויה מתקנים קודם ב-`gh pr edit <N> --title "<title>"`, ואז'
    " `gh pr merge <N> --squash` בלי `--subject` (claude-config#87).\n"
)
REASON_API = (
    "מיזוג עם `commit_title` חסום: כותרת ה-commit נלקחת מכותרת ה-PR.\n"
    "כותרת שגויה מתקנים קודם בכותרת ה-PR, ואז ממזגים בלי `commit_title`"
    " (claude-config#87, #135).\n"
)

API_FIELD_FLAGS = ("-f", "-F", "--raw-field", "--field")

# Shorthand flags of `gh pr merge` that take a value; letters after them are the value.
SHORT_FLAGS_WITH_VALUE = set("AbFRt")
LONG_FLAGS_WITH_VALUE = {
    "--author-email",
    "--body",
    "--body-file",
    "--match-head-commit",
    "--repo",
}


def merge_arguments(words: list[str]) -> list[str] | None:
    """The arguments after `gh pr merge`; None when the command is not a PR merge."""
    subcommand = gh_subcommand(words)
    if subcommand is None or subcommand[:2] != ["pr", "merge"]:
        return None
    return subcommand[2:]


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


def mcp_sets_title(event: dict) -> bool:
    """True for an MCP merge tool called with a commit title."""
    tool_input = event.get("tool_input")
    if not is_mcp_merge(event) or not isinstance(tool_input, dict):
        return False
    return bool(tool_input.get("commit_title"))


def api_sets_title(words: list[str]) -> bool:
    """True for `gh api ... pulls/<N>/merge` with a `commit_title` field."""
    arguments = gh_api_arguments(words) or []
    if not any(MERGE_ENDPOINT.search(argument) for argument in arguments):
        return False
    for index, argument in enumerate(arguments):
        field = None
        if argument in API_FIELD_FLAGS and index + 1 < len(arguments):
            field = arguments[index + 1]
        elif argument.startswith(("-f", "-F")) and len(argument) > 2:
            field = argument[2:]
        elif argument.startswith(("--raw-field=", "--field=")):
            field = argument.split("=", 1)[1]
        if field is not None and field.split("=")[0] == "commit_title":
            return True
    return False


def blocked_reason(event: dict) -> str | None:
    """Why the tool call is blocked; None when it does not set a merge title."""
    if mcp_sets_title(event):
        return REASON_API
    command = shell_command(event)
    if command is None or "merge" not in command:
        return None
    for words in split_subcommands(command):
        arguments = merge_arguments(words)
        if arguments is not None and sets_subject(arguments):
            return REASON
        if api_sets_title(words):
            return REASON_API
    return None


def main() -> int:
    """Read the tool call from stdin; return 2 to block a merge subject, 0 otherwise."""
    event = read_event(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    reason = blocked_reason(event) if event is not None else None
    if reason is None:
        return 0
    sys.stderr.buffer.write(reason.encode("utf-8"))
    sys.stderr.flush()
    return 2


if __name__ == "__main__":
    sys.exit(main())
