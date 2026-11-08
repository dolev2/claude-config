"""PreToolUse hook: asks Dolev before any PR merge.

Wired in settings.json for the Bash and PowerShell tools, and for the GitHub MCP merge
tools (claude-config#135), run by python3 or python, whichever exists, from
$HOME/.claude/hooks/.

Claude Code sends the tool call as JSON on stdin. Exit 0 with no output means no
decision, and the normal permission rules decide. For a merge, the hook prints a
PreToolUse decision of "ask", so an approval window opens even when the session's
permissions allow the call.

`gh pr merge` also has an `ask` rule in settings.json, but a rule matches a prefix and
misses `gh -R a/b pr merge`, `(gh pr merge 5)` or `env gh pr merge 5`; two "ask"
answers to one call open one window. A rule cannot cover the rest either: the MCP
server's name differs between the cloud (`mcp__github__`) and a claude.ai connector on
the computer, and a Bash rule cannot tell `gh api -X PUT .../merge` from a GET on the
same path, which only asks whether the PR was merged (claude-config#163).

This is a guard against mistakes, not a security boundary; the ruleset on the default
branch is (claude-config#162). Not read: the file behind `gh api --input` or
`query=@file` (those GraphQL calls ask anyway), an alias defined outside the command,
and input that is not a JSON object with a string command, which passes: Claude Code
never sends it. A missing Python (exit 127) is shown as a hook error and lets the call
through, on purpose (README).
"""

import json
import re
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
    "מיזוג של PR: צריך את האישור של דולב (rules/git.md).\n"
    "דחייה: עוצרים ומדווחים, ולא ממזגים בדרך אחרת (claude-config#135)."
)

GRAPHQL_MERGE_MUTATIONS = (
    "mergePullRequest",
    "enablePullRequestAutoMerge",
    "mergeBranch",
    "enqueuePullRequest",
)
# POST repos/<owner>/<repo>/merges merges a branch into another without a PR.
BRANCH_MERGE_ENDPOINT = re.compile(r"(^|/)merges/?(\?.*)?$")
FIELD_FLAGS = ("-f", "-F", "--field", "--raw-field", "--input")
# `gh api` options whose value is the next word, so it is not the endpoint.
API_OPTIONS_WITH_VALUE = {
    "-X", "--method", "-f", "-F", "--field", "--raw-field", "-H", "--header",
    "--input", "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p",
    "--preview",
}  # fmt: skip


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


def is_graphql_merge(arguments: list[str]) -> bool:
    """True for a GraphQL merge mutation, or a query read from a file we cannot see."""
    reads_file = "--input" in arguments or any(
        "query=@" in argument for argument in arguments
    )
    return reads_file or any(
        mutation in argument
        for argument in arguments
        for mutation in GRAPHQL_MERGE_MUTATIONS
    )


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


def is_api_merge(arguments: list[str]) -> bool:
    """True for a REST merge (PUT pulls/<N>/merge, POST merges) or a GraphQL one."""
    path = endpoint(arguments) or ""
    if path == "graphql":
        return is_graphql_merge(arguments)
    method = effective_method(arguments)
    if method == "PUT" and MERGE_ENDPOINT.search(path):
        return True
    return method == "POST" and bool(BRANCH_MERGE_ENDPOINT.search(path))


def is_gh_merge(words: list[str]) -> bool:
    """True for `gh [-R repo] pr merge`, or a `gh alias` that may define a merge."""
    arguments = gh_subcommand(words) or []
    if arguments[:2] == ["pr", "merge"]:
        return True
    if arguments[:2] == ["alias", "import"]:
        return True
    return arguments[:2] == ["alias", "set"] and any(
        "merge" in argument for argument in arguments[2:]
    )


def is_shell_merge(command: str) -> bool:
    """True when any subcommand merges a PR, through `gh pr merge` or `gh api`."""
    for words in split_subcommands(command):
        if is_gh_merge(words):
            return True
        arguments = gh_api_arguments(words)
        if arguments is not None and is_api_merge(arguments):
            return True
    return False


def ask_decision() -> str:
    """The PreToolUse output that opens an approval window with the reason."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": REASON,
        }
    }
    return json.dumps(output, ensure_ascii=False)


def main() -> int:
    """Read the tool call from stdin; print an "ask" decision for a merge. Always 0."""
    event = read_event(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    if event is None:
        return 0
    command = shell_command(event)
    if is_mcp_merge(event) or (command is not None and is_shell_merge(command)):
        sys.stdout.buffer.write(ask_decision().encode("utf-8"))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
