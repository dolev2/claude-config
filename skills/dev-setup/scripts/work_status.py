"""The work in the repo at a glance: four Markdown tables, for /status (S-1.41).

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a logged-in
`gh`:

    python "$HOME/.claude/skills/dev-setup/scripts/work_status.py"
    python "$HOME/.claude/skills/dev-setup/scripts/work_status.py" --repo owner/name

The tables: what merged last, what is open in the current sprint, what is blocked or
costs money, and what waits for Dolev. Each row links to the issue's spec part. It only
reads. The sprint picture comes from
sprint_state.state(), the same one the orchestrator reads (S-2.2), so nothing here
ranks or classifies an issue on its own.

Exit codes: 0 with the tables, or with one sentence when the repo has no pipeline;
1 when GitHub could not be read, with no tables, so a partial picture never looks whole.
"""

import argparse
import sys

from gh_rest import api_list, current_repo, gh_api, open_issue_nodes, recent_done
from pipeline_info import REQUIRED_LABELS
from rank_issues import current_sprint, parse_issue, rank, with_started_umbrellas
from spec_check import issue_spec
from spec_toc import part_anchors
from sprint_state import state

TITLE_LIMIT = 50
EMPTY = "אין."
HEADER = "| משימה | תיאור | סטטוס | אפיון |\n|---|---|---|---|"
NO_PART = "—"
RAW = "Accept: application/vnd.github.raw"
STATUS_HE = {
    "explore": "בתכנון",
    "plan-questions": "שאלות לדולב",
    "waiting-approval": "תוכנית לאישור",
    "ready-to-execute": "מוכן לקוד",
    "needs-repair": "לתיקון",
    "in-review": "PR לסקירה",
    "backlog": "בקלוג",
    "done": "Done",
}
NO_PIPELINE = "הצינור לא מותקן בריפו {repo}, ואפשר להתקין אותו ב-dev-setup."
COSTS_MONEY = "עולה כסף, מחכה לאישור"
NOT_READ = "הסקירה לא הוצגה: GitHub לא ענה, ולא נקראו {what}.\n{error}"


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
    heading: str, rows: list[Row], repo: str, anchors: dict[str, dict[str, str]]
) -> str:
    """One section: its heading, then the rows, or one line saying there are none."""
    if not rows:
        return f"### {heading}\n\n{EMPTY}"
    lines = [
        f"| [#{n}](https://github.com/{repo}/issues/{n}) | {short(t)} | {s} "
        f"| {spec_cell(repo, issue, anchors)} |"
        for n, t, s, issue in rows
    ]
    return f"### {heading}\n\n{HEADER}\n" + "\n".join(lines)


def blocked_status(entry: dict) -> str:
    """What a blocked issue waits on: its open blockers, here or in another repo."""
    refs = [f"#{n}" for n in entry["blocked_by"]] + entry["outside_blockers"]
    return "מחכה ל-" + ", ".join(refs)


def sprint_rows(nodes: list[dict], sprint: str) -> list[Row]:
    """The open issues of the sprint, in the order of S-1.42."""
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
) -> str:
    """The four tables as one Markdown text."""
    anchors = anchors or {}
    sprint = current_sprint(nodes)
    done_rows = [
        (i["number"], i["title"], f"Done, {i['closed_at'][:10]}", i) for i in done
    ]
    sections = [table("מה מוזג לאחרונה", done_rows, repo, anchors)]
    if sprint is None:
        sections.append("### מה פתוח בספרינט\n\nאין ספרינט פתוח.")
        picture = {"blocked": [], "on_hold": [], "waiting_dolev": []}
    else:
        picture = state(nodes, sprint, [], lambda pr: {})
        sections.append(
            table(
                f"מה פתוח בספרינט ({sprint})",
                sprint_rows(nodes, sprint),
                repo,
                anchors,
            )
        )
    sections.append(table("מה חסום", held_rows(nodes, picture), repo, anchors))
    by_number = {n["number"]: n for n in nodes}
    waiting = [
        (w["number"], w["title"], status_he(w["status"]), by_number[w["number"]])
        for w in picture["waiting_dolev"]
    ]
    sections.append(table("מה מחכה לדולב", waiting, repo, anchors))
    return "\n\n".join(sections)


def missing_labels(repo: str) -> list[str]:
    """The pipeline labels the repo lacks; none missing means the pipeline is there."""
    names = {label["name"] for label in api_list(f"repos/{repo}/labels?per_page=100")}
    return [name for name in REQUIRED_LABELS if name not in names]


def read(repo: str | None) -> tuple[str, list[str], list[dict], list[dict]]:
    """(repo, missing labels, open issues, last merged), or exits 1 with what failed.

    gh_rest exits with gh's error on a failed call; that exit is turned into a
    message saying which part was not read, instead of a half-built picture.
    """
    what = "פרטי הריפו"
    try:
        repo = repo or current_repo()
        what = "התוויות"
        missing = missing_labels(repo)
        if missing:
            return repo, missing, [], []
        what = "המשימות הפתוחות"
        nodes = open_issue_nodes(repo, with_body=True)
        what = "המשימות שמוזגו"
        return repo, [], nodes, recent_done(repo)
    except SystemExit as failure:
        print(NOT_READ.format(what=what, error=failure.code or ""))
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo", help="owner/name; defaults to the repo of the current directory"
    )
    args = parser.parse_args(argv)

    repo, missing, nodes, done = read(args.repo)
    if missing:
        print(NO_PIPELINE.format(repo=repo))
        return
    print(render(repo, nodes, done, read_anchors(repo, nodes + done)))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
