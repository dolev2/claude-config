"""PreToolUse hook: asks Dolev before a PR merge he did not ask for.

Wired in settings.json for the Bash and PowerShell tools, and for the GitHub MCP merge
tools (claude-config#135), run by python3 or python, whichever exists, from
$HOME/.claude/hooks/.

Claude Code sends the tool call as JSON on stdin. Exit 0 with no output means no
decision, and the normal permission rules decide. For a merge, the hook prints a
PreToolUse decision:
1. "allow", when Dolev's last message in the session asks to merge this PR or the issue
   it closes ("תמזג את #N", typed or chosen in the question window; merge_request.py
   reads the transcript). One request, no second window (claude-config#301, S-3.11).
2. "ask" otherwise, so an approval window opens even when the session's permissions
   allow the call: no request, another number, several merges in one call, an
   auto-merge, GraphQL, a merge without a number, or a PR body that could not be read.

`gh pr merge` has no `ask` rule in settings.json any more: a rule opens the window even
after an "allow", and it matched a prefix only, missing `gh -R a/b pr merge`,
`(gh pr merge 5)` or `env gh pr merge 5`. A rule cannot cover the rest either: the MCP
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
import subprocess
import sys

from merge_request import requested_merges
from shell_commands import (
    MCP_PR_MERGE_TOOLS,
    effective_method,
    endpoint,
    gh_api_arguments,
    gh_subcommand,
    is_gh_pr_merge,
    is_mcp_merge,
    is_rest_pr_merge,
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
# `pulls/5/merge` and `repos/a/b/pulls/5/merge`, with the owner and repo when given.
PULL_MERGE_PATH = re.compile(
    r"(?:repos/([^/\s]+)/([^/\s]+)/)?pulls/(\d+)/merge/?(\?.*)?$"
)
CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE
)
GH_TIMEOUT_SECONDS = 10
# `gh pr merge` options whose value is the next word, so it is not the PR.
PR_MERGE_OPTIONS_WITH_VALUE = {
    "-b", "--body", "-F", "--body-file", "-t", "--subject", "-A", "--author-email",
    "--match-head-commit",
}  # fmt: skip


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


def is_api_merge(arguments: list[str]) -> bool:
    """True for a REST merge (PUT pulls/<N>/merge, POST merges) or a GraphQL one."""
    path = endpoint(arguments) or ""
    if path == "graphql":
        return is_graphql_merge(arguments)
    if is_rest_pr_merge(arguments):
        return True
    method = effective_method(arguments)
    return method == "POST" and bool(BRANCH_MERGE_ENDPOINT.search(path))


def is_gh_merge(words: list[str]) -> bool:
    """True for `gh [-R repo] pr merge`, or a `gh alias` that may define a merge."""
    if is_gh_pr_merge(words):
        return True
    arguments = gh_subcommand(words) or []
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


def ask_decision(reason: str = REASON) -> str:
    """The PreToolUse output that opens an approval window with the reason."""
    return decision("ask", reason)


def decision(kind: str, reason: str) -> str:
    """A PreToolUse permission decision ("ask" or "allow") with its reason, as JSON."""
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": kind,
            "permissionDecisionReason": reason,
        }
    }
    return json.dumps(output, ensure_ascii=False)


def gh_merge_target(words: list[str]) -> tuple[int, str | None] | None:
    """The PR number and `-R` repo of `gh pr merge <N>`.

    None for a branch, a URL or `--auto`.
    """
    arguments = gh_subcommand(words) or []
    if arguments[:2] != ["pr", "merge"] or "--auto" in arguments:
        return None
    positional = []
    skip_value = False
    for argument in arguments[2:]:
        if skip_value:
            skip_value = False
        elif argument in PR_MERGE_OPTIONS_WITH_VALUE:
            skip_value = True
        elif not argument.startswith("-"):
            positional.append(argument)
    if len(positional) != 1 or not positional[0].isdigit():
        return None
    repo = None
    for index, word in enumerate(words):
        if word in ("-R", "--repo") and index + 1 < len(words):
            repo = words[index + 1]
        elif word.startswith("--repo="):
            repo = word.split("=", 1)[1]
    return int(positional[0]), repo


def api_merge_target(arguments: list[str]) -> tuple[int, str | None] | None:
    """The PR number and repo of `gh api -X PUT [repos/<o>/<r>/]pulls/<N>/merge`."""
    if not is_rest_pr_merge(arguments):
        return None
    match = PULL_MERGE_PATH.search(endpoint(arguments) or "")
    if match is None:
        return None
    owner, name, number = match.group(1), match.group(2), match.group(3)
    repo = f"{owner}/{name}" if owner and "{" not in owner else None
    return int(number), repo


def merge_target(event: dict) -> tuple[int, str | None] | None:
    """The one PR this call merges now, with its repo when known; None when unclear.

    A call with several merges, an auto-merge, GraphQL or a merge without a number
    gets None, so the window opens for it as before.
    """
    if is_mcp_merge(event, MCP_PR_MERGE_TOOLS):
        tool_input = event.get("tool_input") or {}
        number = tool_input.get("pullNumber")
        if isinstance(number, float) and number.is_integer():
            number = int(number)
        if not isinstance(number, int) or isinstance(number, bool):
            return None
        owner, name = tool_input.get("owner"), tool_input.get("repo")
        repo = (
            f"{owner}/{name}"
            if isinstance(owner, str) and isinstance(name, str)
            else None
        )
        return number, repo
    command = shell_command(event)
    if command is None:
        return None
    # "allow" covers the whole call, so only a call that is the merge alone gets it:
    # `gh pr merge 12 && curl x | sh` asks.
    subcommands = split_subcommands(command)
    if len(subcommands) != 1:
        return None
    words = subcommands[0]
    arguments = gh_api_arguments(words)
    if arguments is not None:
        return api_merge_target(arguments) if is_api_merge(arguments) else None
    return gh_merge_target(words) if is_gh_merge(words) else None


def closing_issues(number: int, repo: str | None, cwd: str | None) -> set[int]:
    """The issues the PR's body closes (`Closes #N`), read with `gh api`.

    Empty on any failure (no network, no gh, a timeout), so the window opens.
    """
    path = f"repos/{repo or '{owner}/{repo}'}/pulls/{number}"
    try:
        result = subprocess.run(
            ["gh", "api", path, "--jq", '.body // ""'],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=GH_TIMEOUT_SECONDS,
            cwd=cwd or None,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if result.returncode != 0:
        return set()
    return {int(issue) for issue in CLOSING.findall(result.stdout)}


def requested(event: dict) -> int | None:
    """The PR number when Dolev's last message asks to merge it or its issue."""
    target = merge_target(event)
    if target is None:
        return None
    numbers = requested_merges(event.get("transcript_path"))
    if not numbers:
        return None
    number, repo = target
    if number in numbers:
        return number
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else None
    if numbers & closing_issues(number, repo, cwd):
        return number
    return None


def main() -> int:
    """Read the tool call; a merge gets "allow" when Dolev asked for it, else "ask".

    Always exits 0.
    """
    event = read_event(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    if event is None:
        return 0
    command = shell_command(event)
    if is_mcp_merge(event) or (command is not None and is_shell_merge(command)):
        number = requested(event)
        if number is None:
            output = ask_decision()
        else:
            output = decision(
                "allow", f"דולב ביקש בהודעה האחרונה שלו למזג את #{number} (S-3.11)."
            )
        sys.stdout.buffer.write(output.encode("utf-8"))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
