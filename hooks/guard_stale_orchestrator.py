"""PreToolUse, PostToolUse and Stop hook: an orchestrator does not act on stale rules.

CLAUDE.md, rules/ and settings.json load once, when a session starts, and the sprint
orchestrator runs for hours. When a change to them merges meanwhile, it would go on
opening children and merging by the old ones (S-3.10, claude-config#271).

The baseline is the HEAD of ~/.claude the session started from, written by
cloud_refresh.py to the session's marker. "Moved" means a commit on the pipeline's main,
after the baseline, touched SESSION_PATHS, read with git from the cache of
pipeline_shas.py. "An orchestrator" means the transcript has a run of the skill: a
`Skill` call with `dev-orchestrate`, or a `/dev-orchestrate` command. Never a text
search: the name is in every session's skill list and in every child's contract.

Wired in settings.json, run by python3 or python from $HOME/.claude/hooks/:
1. PreToolUse, for `mcp__.*__create_session`, `Bash|PowerShell` and the MCP merge
   tools. Opening a child (the tag `claude-config:orchestrated`) or merging, in a stale
   orchestrator: exit 2, with the reason on stderr.
2. PostToolUse, for `mcp__.*__create_session`. A session opened without that tag, the
   new orchestrator of S-2.12, is the hand-off: it writes the `handed-off` marker.
3. Stop. A stale orchestrator that has not handed off: the turn is blocked once
   (`decision: block`); stop_hook_active lets it end, so it never loops.

Cheap checks first: a cloud session, the baseline marker, a guarded call, an
orchestrator, and only then git. When git fails, or the baseline is not in the cache,
it lets the call pass with no output: sprint_state.py already tells Dolev the check did
not run (S-2.10). Outside a cloud session, and on input that is not a JSON object: 0.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from cloud_refresh import BASELINE_PREFIX, session_marker
from guard_create_session import ORCHESTRATED_TAG, as_strings, is_create_session
from shell_commands import is_mcp_merge, is_shell_pr_merge, read_event, shell_command

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "skills/dev-setup/scripts")
)
import pipeline_shas  # noqa: E402

SKILL = "dev-orchestrate"
COMMAND = re.compile(
    r"^\s*(<command-message>[^<]*</command-message>\s*)?"
    rf"<command-name>/{SKILL}</command-name>"
)
ORCHESTRATOR_PREFIX = "orchestrator"
HANDED_OFF_PREFIX = "handed-off"


def is_cloud() -> bool:
    return os.environ.get("CLAUDE_CODE_REMOTE") == "true"


def is_child_creation(event: dict) -> bool:
    """True for create_session with the orchestrator's child tag."""
    tool_input = event.get("tool_input")
    if not is_create_session(event) or not isinstance(tool_input, dict):
        return False
    return ORCHESTRATED_TAG in as_strings(tool_input.get("tags"))


def is_guarded_call(event: dict) -> bool:
    """True for opening a child or merging a PR, in any way the hooks recognize."""
    if is_child_creation(event) or is_mcp_merge(event):
        return True
    command = shell_command(event)
    return command is not None and "merge" in command and is_shell_pr_merge(command)


def runs_the_skill(entry: object) -> bool:
    """True for a transcript entry that runs dev-orchestrate (Skill call or command)."""
    if not isinstance(entry, dict) or not isinstance(entry.get("message"), dict):
        return False
    content = entry["message"].get("content")
    if entry.get("type") == "user" and isinstance(content, str):
        return bool(COMMAND.match(content))
    if not isinstance(content, list):
        return False
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and entry.get("type") == "user":
            if COMMAND.match(str(block.get("text", ""))):
                return True
        if block.get("type") == "tool_use" and block.get("name") == "Skill":
            skill = (block.get("input") or {}).get("skill")
            if isinstance(skill, str) and skill.lstrip("/") == SKILL:
                return True
    return False


def transcript_runs_the_skill(transcript: Path) -> bool:
    """True when a line of the transcript runs dev-orchestrate. Only lines with the
    name are parsed."""
    with transcript.open(encoding="utf-8", errors="replace") as lines:
        for line in lines:
            if SKILL not in line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if runs_the_skill(entry):
                return True
    return False


def is_orchestrator(event: dict) -> bool:
    """True for a session that ran dev-orchestrate; a yes is kept in a marker."""
    marker = session_marker(ORCHESTRATOR_PREFIX, event.get("session_id"))
    if marker is None:
        return False
    if marker.exists():
        return True
    transcript = event.get("transcript_path")
    if not isinstance(transcript, str) or not Path(transcript).is_file():
        return False
    if not transcript_runs_the_skill(Path(transcript)):
        return False
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("", encoding="utf-8")
    return True


def moved_commit(baseline: str) -> str | None:
    """The newest commit after baseline on main that touched SESSION_PATHS, or None.

    None also when git fails or the cache does not know the baseline.
    """
    cache = pipeline_shas.CACHE
    try:
        pipeline_shas.refresh_cache(cache)
        out = pipeline_shas.git(
            "-C", str(cache), "log", "-1", "--format=%H", f"{baseline}..main",
            "--", *pipeline_shas.SESSION_PATHS,
        )  # fmt: skip
    except (subprocess.SubprocessError, OSError):
        return None
    return out.strip() or None


def baseline_of(event: dict) -> str | None:
    """The sha in the session's baseline marker; None when there is no marker."""
    marker = session_marker(BASELINE_PREFIX, event.get("session_id"))
    if marker is None or not marker.exists():
        return None
    return marker.read_text(encoding="utf-8").strip() or None


def stale_commit(event: dict) -> str | None:
    """The commit that made this orchestrator's rules stale, or None. Cheap checks
    first: the baseline marker, then the transcript, and git last."""
    baseline = baseline_of(event)
    if baseline is None or not is_orchestrator(event):
        return None
    return moved_commit(baseline)


def reason(sha: str, action: str) -> str:
    """The Hebrew reason: what moved, that the rules are stale, and the hand-off."""
    return (
        f"{action}: ההנחיות, הכללים או ההגדרות השתנו ב-main אחרי שהסשן נפתח "
        f"({pipeline_shas.PIPELINE_URL}/commit/{sha}), "
        "והסשן הזה עדיין עובד לפי הגרסה הישנה.\n"
        "מוסרים את הספרינט למתזמר חדש, שייפתח בכללים העדכניים "
        "(`skills/dev-setup/reference/orchestrate.md`, 'שינוי בצינור באמצע ספרינט'; "
        "S-2.12, S-3.10)."
    )


def before_tool(event: dict) -> str | None:
    """The reason to block a guarded call in a stale orchestrator, or None."""
    if not is_guarded_call(event):
        return None
    sha = stale_commit(event)
    if sha is None:
        return None
    action = "פתיחת בן נחסמה" if is_child_creation(event) else "המיזוג נחסם"
    return reason(sha, action)


def after_tool(event: dict) -> None:
    """A session opened without the child tag is the hand-off: mark it."""
    if not is_create_session(event) or is_child_creation(event):
        return
    marker = session_marker(HANDED_OFF_PREFIX, event.get("session_id"))
    if marker is not None:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("", encoding="utf-8")


def at_stop(event: dict) -> str | None:
    """Block the stop once in a stale orchestrator that has not handed off."""
    if event.get("stop_hook_active") is True:
        return None
    handed_off = session_marker(HANDED_OFF_PREFIX, event.get("session_id"))
    if handed_off is None or handed_off.exists():
        return None
    sha = stale_commit(event)
    if sha is None:
        return None
    text = reason(sha, "התור לא נגמר לפני המסירה")
    return json.dumps({"decision": "block", "reason": text}, ensure_ascii=False)


def main() -> int:
    """Read the event from stdin; 2 to block a guarded call, 0 otherwise."""
    event = read_event(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    if event is None or not is_cloud():
        return 0
    name = event.get("hook_event_name")
    try:
        if name == "PreToolUse":
            text = before_tool(event)
            if text is not None:
                sys.stderr.buffer.write(text.encode("utf-8"))
                sys.stderr.flush()
                return 2
        elif name == "PostToolUse":
            after_tool(event)
        elif name == "Stop":
            output = at_stop(event)
            if output is not None:
                sys.stdout.buffer.write(output.encode("utf-8"))
                sys.stdout.flush()
    except OSError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
