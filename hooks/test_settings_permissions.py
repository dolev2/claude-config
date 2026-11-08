"""settings.json: the allow list pre-approves only read or session-only tools.

The list applies on Dolev's computer too, so a tool joins it only together
with this test (#155). The one exception is CHILD_TOOLS, the write tools the
orchestrator's child needs: the service passes a child only tools that are
pre-approved for its parent, so they must be on the list too (#150).
"""

import json
import re
from pathlib import Path

import pytest
from guard_create_session import CHILD_TOOLS

SETTINGS = Path(__file__).resolve().parent.parent / "settings.json"

GITHUB_READ = [
    "get_me",
    "issue_read",
    "pull_request_read",
    "list_issues",
    "list_pull_requests",
    "list_branches",
    "list_commits",
    "get_commit",
    "get_file_contents",
    "get_label",
    "get_check_run",
    "get_job_logs",
    "actions_get",
    "actions_list",
]
SESSION_ONLY = [
    "get_session",
    "list_sessions",
    "list_events",
    "get_event",
    "get_environment",
    "read_documentation",
    "list_triggers",
    "get_trigger",
    "set_session_title",
    "subscribe_pr_activity",
    "unsubscribe_pr_activity",
]
ALLOWED_TOOLS = (
    {f"mcp__github__{name}" for name in GITHUB_READ}
    | {f"mcp__claude-code-remote__{name}" for name in SESSION_ONLY}
    | CHILD_TOOLS
)


def load_settings() -> dict:
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


def merge_hook_matchers(settings: dict) -> list[str]:
    """The PreToolUse matchers of MCP tools that ask_before_merge.py is wired to."""
    return [
        entry["matcher"]
        for entry in settings["hooks"]["PreToolUse"]
        if entry["matcher"].startswith("mcp__")
        and any("ask_before_merge.py" in hook["command"] for hook in entry["hooks"])
    ]


def allow_problems(allow: list[str], merge_matchers: list[str]) -> list[str]:
    """Every reason the allow list breaks the rules; empty when it is fine."""
    problems = []
    for rule in allow:
        if "*" in rule:
            problems.append(f"{rule}: a wildcard pre-approves tools nobody reviewed")
        elif rule not in ALLOWED_TOOLS:
            problems.append(
                f"{rule}: not in ALLOWED_TOOLS. Only tools that read, or touch the "
                "session itself, are pre-approved; add it to the test in the same PR"
            )
        for matcher in merge_matchers:
            if re.fullmatch(matcher, rule):
                problems.append(f"{rule}: ask_before_merge.py guards it")
    return problems


def test_current_allow_list_is_valid():
    settings = load_settings()
    allow = settings["permissions"]["allow"]
    assert allow_problems(allow, merge_hook_matchers(settings)) == []
    assert len(allow) == len(set(allow))


def test_every_child_tool_is_pre_approved():
    # Without it, create_session drops the tool and the child stops on a prompt.
    missing = sorted(CHILD_TOOLS - set(load_settings()["permissions"]["allow"]))
    assert missing == [], f"add to permissions.allow in settings.json: {missing}"


def test_merge_hook_is_still_wired():
    assert merge_hook_matchers(load_settings()), (
        "ask_before_merge.py lost its MCP matcher"
    )


@pytest.mark.parametrize(
    ("rule", "reason"),
    [
        ("mcp__github__*", "wildcard"),
        ("mcp__github__issue_write", "not in ALLOWED_TOOLS"),
        ("mcp__claude-code-remote__send_later", "not in ALLOWED_TOOLS"),
        ("mcp__github__merge_pull_request", "ask_before_merge.py"),
        ("Bash(gh api *)", "wildcard"),
        ("Bash", "not in ALLOWED_TOOLS"),
    ],
)
def test_bad_rule_is_rejected(rule, reason):
    problems = allow_problems([rule], merge_hook_matchers(load_settings()))
    assert any(reason in problem for problem in problems), problems
