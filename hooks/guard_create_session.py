"""PreToolUse hook: asks Dolev before a child session gets more than it needs.

Wired in settings.json for `mcp__.*__create_session`, since the server's name can
change (the same reason as in ask_before_merge.py), run by python3 or python from
$HOME/.claude/hooks/ (claude-config#175).

It prints an "ask" decision when `extra_allowed_tools` holds a tool outside
CHILD_TOOLS (this catches `Bash(...)`, `*` and any other write tool without a block
list), or when `environment_id` is set: a hook cannot call an MCP tool to learn the
caller's environment, and without the field the child inherits it. The reason names
what it caught. Otherwise it prints nothing, and the normal permission rules decide.

This is a guard against mistakes, not a security boundary: the service already passes
a child only tools that are pre-approved for the session that opens it (cloud.md,
"חלונות אישור בסשן-בן"). Input that is not a JSON object passes; exit is always 0.
"""

import sys

from ask_before_merge import ask_decision
from shell_commands import read_event

# What the orchestrator's child needs beyond the allow list in settings.json (#150).
# No send_message: the service raises a prompt on it anyway, so a child reports on
# GitHub instead and the orchestrator polls it (#184).
CHILD_TOOLS = frozenset(
    {
        "mcp__github__create_pull_request",
        "mcp__github__update_pull_request",
        "mcp__github__add_issue_comment",
    }
)


def is_create_session(event: dict) -> bool:
    """True for the create_session tool of any MCP server."""
    name = event.get("tool_name")
    return (
        isinstance(name, str)
        and name.startswith("mcp__")
        and name.endswith("__create_session")
    )


def extra_tools(tool_input: dict) -> list[str]:
    """The tools in `extra_allowed_tools`, as strings; a lone string counts as one."""
    tools = tool_input.get("extra_allowed_tools") or []
    if isinstance(tools, str):
        tools = [tools]
    if not isinstance(tools, list):
        return [str(tools)]
    return [str(tool) for tool in tools]


def broad_grants(tool_input: dict) -> list[str]:
    """One Hebrew line for each grant beyond what the child needs; empty when none."""
    reasons = [
        f"הבן יקבל `{tool}`"
        for tool in extra_tools(tool_input)
        if tool not in CHILD_TOOLS
    ]
    if tool_input.get("environment_id"):
        reasons.append(f"הבן ייפתח בסביבה אחרת (`{tool_input['environment_id']}`)")
    return reasons


def reason_text(grants: list[str]) -> str:
    """The approval window's text: what passes to the child, one line each."""
    lines = "\n".join(f"{index}. {grant}." for index, grant in enumerate(grants, 1))
    return (
        "פתיחת סשן-בן עם יותר ממה שהבן של המתזמר צריך:\n"
        f"{lines}\n"
        "דחייה: הסשן לא נפתח (claude-config#175)."
    )


def main() -> int:
    """Read the tool call from stdin; print an "ask" for broad grants. Always 0."""
    event = read_event(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    if event is None or not is_create_session(event):
        return 0
    tool_input = event.get("tool_input")
    grants = broad_grants(tool_input) if isinstance(tool_input, dict) else []
    if grants:
        sys.stdout.buffer.write(ask_decision(reason_text(grants)).encode("utf-8"))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
