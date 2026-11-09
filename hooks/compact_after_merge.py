"""PostToolUse and Stop hook: after a PR merge, the turn ends with a /compact block.

The rule is in the global CLAUDE.md ("מה פתוח"), and it was forgotten after three
merges in a row (claude-config#199). A hook cannot run /compact itself, only remind.

Wired in settings.json, run by python3 or python, whichever exists, from
$HOME/.claude/hooks/:
1. PostToolUse, for Bash and PowerShell and for the GitHub MCP merge tool. On a call
   that surely merged a PR (`gh pr merge`, a REST PUT to pulls/<N>/merge, the MCP
   `merge_pull_request`; not auto-merge, which happens later), it writes a marker for
   the session and returns a reminder as additionalContext. PostToolUse runs only after
   a call that succeeded: a failed or declined merge fires PostToolUseFailure, so it
   leaves no marker (checked in a cloud session, 9.11.2026).
2. Stop, with no matcher. With no marker it does nothing. When the last message has a
   code block whose first line starts with /compact, it removes the marker. Otherwise it
   blocks the stop once, with what to add; when Claude stops again (stop_hook_active),
   it removes the marker and lets the turn end, so it never loops.

Input that is not a JSON object, a missing session_id, or a marker it cannot write:
exit 0 with no output, like the other hooks.
"""

import json
import re
import sys
import tempfile
from pathlib import Path

from shell_commands import (
    MCP_PR_MERGE_TOOLS,
    is_mcp_merge,
    is_shell_pr_merge,
    read_event,
    shell_command,
)

REMINDER = (
    "PR מוזג. ההודעה האחרונה של התור נגמרת ב'מה פתוח' עם בלוק `/compact` מלא "
    "(CLAUDE.md הגלובלי, 'מה פתוח'; claude-config#199)."
)
STOP_REASON = (
    "מוזג PR בתור הזה, וההודעה האחרונה בלי בלוק `/compact`. "
    "הוסף את החלק 'מה פתוח' עם בלוק קוד אחד שמתחיל ב-`/compact`, "
    "ואחריו התקציר בעברית (CLAUDE.md הגלובלי, 'מה פתוח'; claude-config#199)."
)
# A fenced code block (``` or ~~~) whose first non-empty line starts with /compact.
COMPACT_BLOCK = re.compile(r"^[ \t]*(```|~~~)[^\n]*\n\s*/compact\b", re.MULTILINE)
UNSAFE_ID_CHARACTERS = re.compile(r"[^A-Za-z0-9-]")


def marker_dir() -> Path:
    """The folder of the session markers, under the system's temp folder."""
    return Path(tempfile.gettempdir()) / "claude-hooks"


def marker_path(event: dict) -> Path | None:
    """The marker file of the event's session; None without a usable session_id."""
    session_id = event.get("session_id")
    if not isinstance(session_id, str):
        return None
    safe_id = UNSAFE_ID_CHARACTERS.sub("", session_id)
    return marker_dir() / f"compact-{safe_id}" if safe_id else None


def is_merge_call(event: dict) -> bool:
    """True for a tool call that surely merged a PR, by MCP or by a shell command."""
    if is_mcp_merge(event, MCP_PR_MERGE_TOOLS):
        return True
    command = shell_command(event)
    return command is not None and is_shell_pr_merge(command)


def has_compact_block(message: object) -> bool:
    """True when the message has a code block that starts with /compact."""
    return isinstance(message, str) and bool(COMPACT_BLOCK.search(message))


def after_tool(event: dict, marker: Path) -> str | None:
    """Mark the session after a merge; the reminder to print, or None."""
    if not is_merge_call(event):
        return None
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("merged\n", encoding="utf-8")
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": REMINDER,
        }
    }
    return json.dumps(output, ensure_ascii=False)


def at_stop(event: dict, marker: Path) -> str | None:
    """Block the stop once when a merge has no /compact block; the output, or None."""
    if not marker.exists():
        return None
    if event.get("stop_hook_active") is True or has_compact_block(
        event.get("last_assistant_message")
    ):
        marker.unlink(missing_ok=True)
        return None
    return json.dumps({"decision": "block", "reason": STOP_REASON}, ensure_ascii=False)


def respond(event: dict) -> str | None:
    """The hook's output for the event, by its hook_event_name; None for no output."""
    marker = marker_path(event)
    if marker is None:
        return None
    name = event.get("hook_event_name")
    if name == "PostToolUse":
        return after_tool(event, marker)
    if name == "Stop":
        return at_stop(event, marker)
    return None


def main() -> int:
    """Read the event from stdin and print the hook's output, if any. Always 0."""
    event = read_event(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    if event is None:
        return 0
    try:
        output = respond(event)
    except OSError:
        return 0
    if output is not None:
        sys.stdout.buffer.write(output.encode("utf-8"))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
