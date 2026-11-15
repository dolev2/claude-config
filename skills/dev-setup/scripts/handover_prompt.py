"""The opening prompt of a new sprint orchestrator, built from data (S-2.12).

When an orchestrator must be replaced (rules loaded at its start changed, or the
refresh failed), it opens a new orchestrator with this prompt and archives itself
(`orchestrate.md`, "שינוי בצינור באמצע ספרינט"). The agent does not write the prompt:
it passes data, and this script lays it out in one fixed shape (Dolev's decision 3 on
claude-config #269). Stdlib only, with a logged-in `gh`:

    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/handover_prompt.py" --status-line "since ... session_sha ..." \
      --state state.json --children session_01=12,session_02=15 \
      --session session_00 --started 2026-11-15T08:00:00Z \
      --moved <sha> --notes notes.md > prompt.md

--state is the output of sprint_state.py from the current check, so GitHub is read
once more only for the children's issues and what merged since --started. The
children come from list_sessions, an MCP tool, so the agent passes them in. --notes is
the only text the agent writes: what Dolev said in the chat and is not on GitHub.
What the new orchestrator does with the prompt is S-2.13, claude-config #273.
"""

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from gh_rest import current_repo
from pipeline_shas import PIPELINE_URL
from sprint_github import done_since, issue_summary

OPENING = "תריץ את הספרינט"
NONE = "אין."
WORK = {
    "status:explore": "תכנון",
    "status:ready-to-execute": "קוד",
    "status:needs-repair": "תיקון",
    "status:backlog": "אפיון",
}
DOLEV_STAGES = {
    "questions": "שאלות על האפיון",
    "review": "PR של אפיון לסקירה",
    "breakdown": "אפיון שמוזג ומחכה לפירוק",
    "replan": "חלק פתוח כבר מצביע עליה: להחזיר לתכנון",
}


def children_list(text: str) -> list[tuple[str, int]]:
    """--children: `<session_id>=<N>,...`; an empty string is none."""
    found = []
    for part in filter(None, (p.strip() for p in text.split(","))):
        session, sep, number = part.partition("=")
        if not sep or not session.strip() or not number.strip().isdigit():
            message = f"not <session_id>=<issue number>: {part}"
            raise argparse.ArgumentTypeError(message)
        found.append((session.strip(), int(number)))
    return found


def numbered(lines: list[str]) -> list[str]:
    """A numbered Markdown list, or the single line "אין." when there is nothing."""
    return [f"{i}. {line}" for i, line in enumerate(lines, 1)] or [NONE]


def child_line(session: str, issue: dict, prs: dict[int, int]) -> str:
    """One child: its session, the issue with title and label, its work, and a PR."""
    status = issue["status"] or "בלי תווית status"
    work = WORK.get(issue["status"] or "", "מחכה לדולב")
    line = f"`{session}`: #{issue['number']} {issue['title']} (`{status}`), {work}"
    pr = prs.get(issue["number"])
    return f"{line}, PR #{pr}." if pr else f"{line}."


def waiting_lines(state: dict) -> list[str]:
    """What waits for Dolev: his-turn issues, the merge queue, and proposal stages."""
    lines = [
        f"#{i['number']} {i['title']} (`status:{i['status']}`)"
        for i in state.get("waiting_dolev", [])
    ]
    lines += [
        f"למיזוג: PR #{q['pr']} של #{q['number']}, CI {q.get('ci', '?')}, "
        f"mergeable_state {q.get('mergeable_state', '?')}"
        for q in state.get("merge_queue", [])
    ]
    lines += [
        f"הצעה #{p['number']} {p['title']}: {DOLEV_STAGES[p['stage']]}"
        for p in state.get("proposals", [])
        if p.get("stage") in DOLEV_STAGES
    ]
    return lines


def reason_line(moved: str | None, reason: str | None) -> str:
    """Why: the commit that moved session_sha, or why the refresh failed."""
    if moved:
        return (
            "השתנו הנחיות, כללים או הגדרות שנטענים רק בפתיחת סשן: "
            f"[{moved[:7]}]({PIPELINE_URL}/commit/{moved})."
        )
    return f"הרענון של `~/.claude` נכשל: {reason}"


def prompt(
    args: argparse.Namespace,
    state: dict,
    issue_of: Callable[[int], dict],
    merged: list[dict],
) -> str:
    """The whole prompt, in the order of S-2.12; GitHub reads are passed in."""
    prs = {q["number"]: q["pr"] for q in state.get("merge_queue", [])}
    children = [child_line(s, issue_of(n), prs) for s, n in args.children]
    followed = [
        f"PR #{q['pr']} של #{q['number']}" for q in state.get("merge_queue", [])
    ]
    notes = args.notes.read_text(encoding="utf-8").strip() if args.notes else ""
    parts = [
        OPENING,
        "",
        "## מסירה ממתזמר קודם",
        "",
        f"הסיבה: {reason_line(args.moved, args.reason)}",
        "",
        f"המתזמר הקודם: `{args.session}`, נפתח ב-{args.started}. "
        "הוא עובר לארכיון אחרי שהסשן הזה עולה.",
        "",
        f"הספרינט: {state.get('sprint', '?')}.",
        "",
        "### שורת המצב של הבדיקה האחרונה",
        "",
        "```text",
        args.status_line,
        "```",
        "",
        "### הבנים שרצים",
        "",
        *numbered(children),
        "",
        "### ה-PRים שהמתזמר הקודם עקב אחריהם",
        "",
        "ההרשמה לאירועים שלהם בוטלה, וצריך להירשם אליהם מחדש.",
        "",
        *numbered(followed),
        "",
        "### מה מוזג בסשן",
        "",
        *numbered([f"#{i['number']} {i['title']}" for i in merged]),
        "",
        "### מה מחכה לדולב",
        "",
        *numbered(waiting_lines(state)),
        "",
        "### מה דולב אמר בשיחה ולא נכתב ב-GitHub",
        "",
        notes or NONE,
    ]
    return "\n".join(parts) + "\n"


def parse(argv: list[str] | None) -> argparse.Namespace:
    """The arguments; --state is read and parsed here, so a bad file exits at once."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--status-line", required=True, help="the last check's line")
    parser.add_argument("--state", required=True, type=Path, help="sprint_state.py")
    parser.add_argument("--children", type=children_list, default=[])
    parser.add_argument("--session", required=True, help="this session's id")
    parser.add_argument("--started", required=True, help="when it opened (ISO)")
    why = parser.add_mutually_exclusive_group(required=True)
    why.add_argument("--moved", help="the commit that moved session_sha")
    why.add_argument("--reason", help="why the refresh failed")
    parser.add_argument("--notes", type=Path, help="what Dolev said in the chat")
    parser.add_argument("--repo", help="owner/name; defaults to the current repo")
    args = parser.parse_args(argv)
    try:
        args.state_data = json.loads(args.state.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        parser.error(f"--state is not a readable JSON file: {err}")
    if not isinstance(args.state_data, dict):
        parser.error("--state is not the JSON object sprint_state.py prints")
    if args.notes and not args.notes.is_file():
        parser.error(f"--notes is not a file: {args.notes}")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse(argv)
    repo = args.repo or current_repo()
    state = args.state_data
    merged = done_since(repo, state.get("sprint", ""), args.started)
    text = prompt(args, state, lambda n: issue_summary(repo, n), merged)
    sys.stdout.write(text)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
