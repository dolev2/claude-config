"""PreToolUse hook: asks Dolev before any PR merge that is not `gh pr merge`.

Wired in settings.json for the Bash and PowerShell tools, and for the GitHub MCP merge
tools (claude-config#135), run by python3 or python, whichever exists, from
$HOME/.claude/hooks/.

Claude Code sends the tool call as JSON on stdin. Exit 0 with no output means no
decision, and the normal permission rules decide. For a merge, the hook prints a
PreToolUse decision of "ask", so an approval window opens even when the session's
permissions allow the call.

`gh pr merge` has its own `ask` rule in settings.json and is not checked here. A rule
cannot cover the rest: the MCP server's name differs between the cloud (`mcp__github__`)
and a claude.ai connector on the computer, and a Bash rule cannot tell `gh api -X PUT
.../merge` from a GET on the same path, which only asks whether the PR was merged. This
is a guard against mistakes, not a security boundary: `sh -c` and `--input` are not
read.
"""

import json
import re
import sys
from pathlib import PurePath

from shell_commands import read_event, shell_command, split_subcommands, strip_prefixes

REASON = (
    "מיזוג של PR: צריך את האישור של דולב (rules/git.md).\n"
    "דחייה: עוצרים ומדווחים, ולא ממזגים בדרך אחרת (claude-config#135)."
)

MCP_MERGE_TOOLS = ("__merge_pull_request", "__enable_pr_auto_merge")
GRAPHQL_MERGE_MUTATIONS = ("mergePullRequest", "enablePullRequestAutoMerge")
# `pulls/5/merge`, `/repos/a/b/pulls/5/merge`, a full URL, with or without a query.
MERGE_ENDPOINT = re.compile(r"(^|/)pulls/\d+/merge/?(\?.*)?$")


def is_mcp_merge(event: dict) -> bool:
    """True for an MCP tool that merges a PR or turns on its auto-merge."""
    name = event.get("tool_name")
    return (
        isinstance(name, str)
        and name.startswith("mcp__")
        and name.endswith(MCP_MERGE_TOOLS)
    )


def api_arguments(words: list[str]) -> list[str] | None:
    """The arguments after `gh api`; None when the command is not `gh api`."""
    words = strip_prefixes(words)
    if len(words) < 2 or PurePath(words[0]).name.lower() not in ("gh", "gh.exe"):
        return None
    return words[2:] if words[1] == "api" else None


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


def is_api_merge(arguments: list[str]) -> bool:
    """True for a REST merge (PUT on pulls/<N>/merge) or a GraphQL merge mutation."""
    if arguments and arguments[0] == "graphql":
        return any(
            mutation in argument
            for argument in arguments
            for mutation in GRAPHQL_MERGE_MUTATIONS
        )
    has_endpoint = any(MERGE_ENDPOINT.search(argument) for argument in arguments)
    return has_endpoint and http_method(arguments) == "PUT"


def is_shell_merge(command: str) -> bool:
    """True when any subcommand merges a PR through `gh api`."""
    if "merge" not in command.lower():
        return False
    for words in split_subcommands(command):
        arguments = api_arguments(words)
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
