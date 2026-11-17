"""The work in the repo at a glance: four tables and a graph, for /status (S-1.41).

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a logged-in
`gh`:

    python "$HOME/.claude/skills/dev-setup/scripts/work_status.py"
    python "$HOME/.claude/skills/dev-setup/scripts/work_status.py" --repo owner/name
    python "$HOME/.claude/skills/dev-setup/scripts/work_status.py" --which

Which repo (S-1.56): --repo, else the repo of the current directory, else the first
repo in the session's sources (--source-repo, read by the status skill), else one
sentence saying there is no repo to show. --which prints only the chosen repo.

The tables: what merged last, what is open in the current sprint, what is blocked or
costs money, and what waits for Dolev. Each row links to the issue's spec part. Then the
sprint's blocking graph, as a Mermaid block (status_graph.py, S-1.48). It only reads
GitHub. The --sessions file (status_sessions.py) puts the issues with an active session
first, marked "פעיל" (S-1.57). With --page it also writes the clickable graph
(status_page.py, S-1.50), with the session links, for the status skill to publish.
The sprint picture comes from sprint_state.state(), the same one the orchestrator
reads (S-2.2), so nothing here ranks or classifies an issue on its own.

Exit codes: 0 with the tables, with one sentence when the repo has no pipeline, or
with only the repo under --which;
1 when GitHub could not be read, with no tables, so a partial picture never looks whole;
2 when the --sessions file is broken; 3 when there is no repo to show.
"""

import argparse
import sys
from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import Path

import billing_flag
from gh_rest import (
    api_list,
    gh_api,
    open_issue_nodes,
    recent_done,
    repo_from_url,
    repo_of_folder,
)
from pipeline_info import REQUIRED_LABELS
from rank_issues import current_sprint, parse_issue, rank, with_started_umbrellas
from spec_check import issue_spec
from spec_toc import part_anchors
from sprint_state import state
from status_graph import EMPTY, NO_SPRINT, graph, layout
from status_page import page
from status_sessions import ACTIVE_MARK, Sessions, read_sessions

TITLE_LIMIT = 50
HEADER = "| משימה | תיאור | סטטוס | אפיון |\n|---|---|---|---|"
NO_PART = "—"
RAW = "Accept: application/vnd.github.raw"
STATUS_HE = {
    "explore": "בתכנון",
    "plan-questions": "שאלות לדולב",
    "ready-to-execute": "מוכן לקוד",
    "needs-repair": "לתיקון",
    "in-review": "PR לסקירה",
    "backlog": "בקלוג",
    "done": "Done",
}
NO_PIPELINE = "הצינור לא מותקן בריפו {repo}, ואפשר להתקין אותו ב-dev-setup."
COSTS_MONEY = "עולה כסף, מחכה לאישור"
NOT_READ = "הסקירה של {repo} לא הוצגה: GitHub לא ענה, ולא נקראו {what}.\n{error}"
REPO_LINE = "**הריפו:** [{repo}](https://github.com/{repo})"
NO_REPO = "אין ריפו לסקור: התיקייה של הסשן לא בתוך ריפו של GitHub, {reason}."
NO_SOURCES = "ולסשן אין ריפו במקורות"
SOURCES_UNREAD = "והמקורות של הסשן לא נקראו"
SESSIONS_NOT_READ = 'רשימת הסשנים לא נקראה, ולכן אין סימן "פעיל".'


def choose_repo(
    repo: str | None, folder_repo: str | None, source_repo: str | None
) -> str | None:
    """The repo to show (S-1.56): the one asked for, the folder's, then the source's.

    The folder wins over the sources, so a session that sits in a repo never shows
    another one. A source given as its full GitHub URL is cut to owner/name. None
    means there is no repo to show.
    """
    if source_repo:
        source_repo = repo_from_url(source_repo) or source_repo
    return repo or folder_repo or source_repo or None


def no_repo(sources_unread: bool) -> str:
    """The one sentence for a session with no repo to show, with the reason."""
    return NO_REPO.format(reason=SOURCES_UNREAD if sources_unread else NO_SOURCES)


def short(title: str, limit: int = TITLE_LIMIT) -> str:
    """The title cut to `limit` characters with an ellipsis, and safe inside a table."""
    title = title.replace("|", "\\|").strip()
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


def status_he(status: str | None) -> str:
    """The status label in Hebrew; an issue with no status label says so."""
    return STATUS_HE.get(status, status) if status else "בלי סטטוס"


def spec_of(issue: dict) -> tuple[str, list[str]] | None:
    """(spec path, part ids) from the "אפיון:" line, or None without a full line."""
    line = issue_spec(issue) if issue.get("body") else None
    return line if line and line[0] and line[1] else None


def spec_cell(repo: str, issue: dict, anchors: dict[str, dict[str, str]]) -> str:
    """Links to the issue's spec parts, or a dash when it has none (a backlog proposal).

    A part whose heading was not found links to the spec file itself, so the cell
    still leads somewhere.
    """
    line = spec_of(issue)
    if not line:
        return NO_PART
    path, ids = line
    url = f"https://github.com/{repo}/blob/HEAD/{path}"
    slugs = anchors.get(path, {})
    return ", ".join(
        f"[{i}]({url}#{slugs[i]})" if i in slugs else f"[{i}]({url})" for i in ids
    )


def read_anchors(repo: str, issues: list[dict]) -> dict[str, dict[str, str]]:
    """{spec path: {part id: anchor}} for every spec file the issues point to.

    A file that cannot be read (not on the default branch yet) gets no anchors: its
    parts link to the file, and the tables are still whole.
    """
    paths = {line[0] for line in map(spec_of, issues) if line}
    found = {}
    for path in sorted(paths):
        try:
            found[path] = part_anchors(
                gh_api(f"repos/{repo}/contents/{path}", "-H", RAW)
            )
        except SystemExit:
            found[path] = {}
    return found


Row = tuple[int, str, str, dict]


def table(
    heading: str,
    rows: list[Row],
    repo: str,
    anchors: dict[str, dict[str, str]],
    active: Collection[int] = (),
) -> str:
    """One section: its heading, then the rows, or one line saying there are none.

    The issues in `active` (an active session, S-1.57) come first, in the same order
    among themselves, with "פעיל" after the status, in the same column.
    """
    if not rows:
        return f"### {heading}\n\n{EMPTY}"
    rows = sorted(rows, key=lambda row: row[0] not in active)
    lines = [
        f"| [#{n}](https://github.com/{repo}/issues/{n}) | {short(t)} "
        f"| {s}{ACTIVE_MARK if n in active else ''} "
        f"| {spec_cell(repo, issue, anchors)} |"
        for n, t, s, issue in rows
    ]
    return f"### {heading}\n\n{HEADER}\n" + "\n".join(lines)


def blocked_status(entry: dict) -> str:
    """What a blocked issue waits on: its open blockers, here or in another repo."""
    refs = [f"#{n}" for n in entry["blocked_by"]] + entry["outside_blockers"]
    return "מחכה ל-" + ", ".join(refs)


def sprint_rows(nodes: list[dict], sprint: str) -> list[Row]:
    """The open issues of the sprint, in the order of S-1.3."""
    in_sprint = [
        n for n in nodes if n["milestone"] and n["milestone"]["title"] == sprint
    ]
    by_number = {n["number"]: n for n in in_sprint}
    return [
        (i.number, i.title, status_he(i.status), by_number[i.number])
        for i in rank(
            with_started_umbrellas([parse_issue(n) for n in in_sprint], nodes)
        )
    ]


def held_rows(nodes: list[dict], picture: dict) -> list[Row]:
    """The blocked issues with what they wait on, then those that cost money.

    An issue can be both: it gets one row, with both reasons.
    """
    by_number = {n["number"]: n for n in nodes}
    costs = set(picture["on_hold"])
    rows = [
        (
            b["number"],
            by_number[b["number"]]["title"],
            blocked_status(b) + (", ועולה כסף" if b["number"] in costs else ""),
            by_number[b["number"]],
        )
        for b in picture["blocked"]
    ]
    blocked = {b["number"] for b in picture["blocked"]}
    rows += [
        (n, by_number[n]["title"], COSTS_MONEY, by_number[n])
        for n in picture["on_hold"]
        if n not in blocked
    ]
    return rows


def render(
    repo: str,
    nodes: list[dict],
    done: list[dict],
    anchors: dict[str, dict[str, str]] | None = None,
    billing: dict | None = None,
    sessions: Sessions | None = None,
) -> str:
    """The four tables and the blocking graph as one Markdown text.

    `billing` is the billing flag while it is on (billing_flag.current()): its line
    comes before the tables (S-1.53). `sessions` (status_sessions.by_issue) puts the
    issues with an active session first; None means the list was not read, and a line
    under the repo line says so (S-1.57).
    """
    anchors = anchors or {}
    active = set(sessions or {})
    sprint = current_sprint(nodes)
    done_rows = [
        (i["number"], i["title"], f"Done, {i['closed_at'][:10]}", i) for i in done
    ]
    sections = [table("מה מוזג לאחרונה", done_rows, repo, anchors)]
    if sprint is None:
        sections.append(f"### מה פתוח בספרינט\n\n{NO_SPRINT}")
        picture = {"blocked": [], "on_hold": [], "waiting_dolev": []}
        sprint_nodes = None
    else:
        picture = state(nodes, sprint, [], lambda pr: {})
        rows = sprint_rows(nodes, sprint)
        sprint_nodes = [issue for *_, issue in rows]
        sections.append(
            table(f"מה פתוח בספרינט ({sprint})", rows, repo, anchors, active)
        )
    sections.append(table("מה חסום", held_rows(nodes, picture), repo, anchors, active))
    by_number = {n["number"]: n for n in nodes}
    waiting = [
        (w["number"], w["title"], status_he(w["status"]), by_number[w["number"]])
        for w in picture["waiting_dolev"]
    ]
    sections.append(table("מה מחכה לדולב", waiting, repo, anchors, active))
    sections.append(graph(sprint_nodes, nodes, status_he, active))
    unread = [SESSIONS_NOT_READ] if sessions is None else []
    notice = [billing["notice"]] if billing else []
    return "\n\n".join([REPO_LINE.format(repo=repo), *unread, *notice, *sections])


def sprint_issues(nodes: list[dict]) -> list[dict] | None:
    """The sprint's open issues in the table's order, or None with no open sprint."""
    sprint = current_sprint(nodes)
    if sprint is None:
        return None
    return [issue for *_, issue in sprint_rows(nodes, sprint)]


def write_page(
    path: str, repo: str, nodes: list[dict], sessions: Sessions | None
) -> None:
    """The clickable graph (S-1.50), from the same picture as the chat graph."""
    issues = sprint_issues(nodes)
    active = set(sessions or {})
    shape = None if issues is None else layout(issues, nodes, status_he, active)
    updated = datetime.now(UTC).isoformat(timespec="minutes")
    text = page(repo, shape, nodes, sessions, updated)
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def missing_labels(repo: str) -> list[str]:
    """The pipeline labels the repo lacks; none missing means the pipeline is there."""
    names = {label["name"] for label in api_list(f"repos/{repo}/labels?per_page=100")}
    return [name for name in REQUIRED_LABELS if name not in names]


def read(repo: str) -> tuple[list[str], list[dict], list[dict]]:
    """(missing labels, open issues, last merged), or exits 1 with what failed.

    gh_rest exits with gh's error on a failed call; that exit is turned into a
    message saying which part of which repo was not read, instead of a half-built
    picture.
    """
    what = "התוויות"
    try:
        missing = missing_labels(repo)
        if missing:
            return missing, [], []
        what = "המשימות הפתוחות"
        nodes = open_issue_nodes(repo, with_body=True)
        what = "המשימות שמוזגו"
        return [], nodes, recent_done(repo)
    except SystemExit as failure:
        print(NOT_READ.format(repo=repo, what=what, error=failure.code or ""))
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo",
        help="owner/name; defaults to the repo of the current directory, "
        "then to --source-repo",
    )
    parser.add_argument(
        "--source-repo",
        help="owner/name of the first repo in the session's sources, used only "
        "when the current directory is not in a GitHub repo",
    )
    parser.add_argument(
        "--sources-unread",
        action="store_true",
        help="the session's sources could not be read (says why there is no repo)",
    )
    parser.add_argument(
        "--which", action="store_true", help="print only the chosen repo, and stop"
    )
    parser.add_argument(
        "--page", help="also write the clickable graph page (S-1.50) to this file"
    )
    parser.add_argument(
        "--sessions",
        help="JSON [{id, title, tags, session_status, created_at}]: every row "
        "list_sessions returned, unfiltered",
    )
    args = parser.parse_args(argv)

    folder = None if args.repo else repo_of_folder()
    repo = choose_repo(args.repo, folder, args.source_repo)
    if repo is None:
        print(no_repo(args.sources_unread))
        sys.exit(3)
    if args.which:
        print(repo)
        return
    sessions = read_sessions(args.sessions, repo) if args.sessions else None
    missing, nodes, done = read(repo)
    if missing:
        print(NO_PIPELINE.format(repo=repo))
        return
    if args.page:
        write_page(args.page, repo, nodes, sessions)
    anchors = read_anchors(repo, nodes + done)
    print(render(repo, nodes, done, anchors, billing_flag.current(), sessions))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
