"""The work in the repo at a glance: four Markdown tables, for /status (S-1.41).

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a logged-in
`gh`:

    python "$HOME/.claude/skills/dev-setup/scripts/work_status.py"
    python "$HOME/.claude/skills/dev-setup/scripts/work_status.py" --repo owner/name

The tables: what merged last, what is open in the current sprint, what is blocked or
costs money, and what waits for Dolev. It only reads. The sprint picture comes from
sprint_state.state(), the same one the orchestrator reads (S-2.2), so nothing here
ranks or classifies an issue on its own.

Exit codes: 0 with the tables, or with one sentence when the repo has no pipeline;
1 when GitHub could not be read, with no tables, so a partial picture never looks whole.
"""

import argparse
import sys

from gh_rest import api_list, current_repo, open_issue_nodes, recent_done
from pipeline_info import REQUIRED_LABELS
from rank_issues import current_sprint, parse_issue, rank
from sprint_state import state

TITLE_LIMIT = 50
EMPTY = "אין."
HEADER = "| משימה | תיאור | סטטוס |\n|---|---|---|"
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
NO_PIPELINE = (
    "הצינור לא מותקן בריפו {repo}, ולכן אין סקירה. "
    "כדי להתקין אותו: dev-setup (חסרות התוויות: {labels})."
)
NOT_READ = "הסקירה לא הוצגה: GitHub לא ענה, ולא נקראו {what}.\n{error}"


def short(title: str, limit: int = TITLE_LIMIT) -> str:
    """The title cut to `limit` characters with an ellipsis, and safe inside a table."""
    title = title.replace("|", "\\|").strip()
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


def status_he(status: str | None) -> str:
    """The status label in Hebrew; an issue with no status label says so."""
    return STATUS_HE.get(status, status) if status else "בלי סטטוס"


def table(heading: str, rows: list[tuple[int, str, str]], repo: str) -> str:
    """One section: its heading, then the rows, or one line saying there are none."""
    if not rows:
        return f"### {heading}\n\n{EMPTY}"
    lines = [
        f"| [#{n}](https://github.com/{repo}/issues/{n}) | {short(t)} | {s} |"
        for n, t, s in rows
    ]
    return f"### {heading}\n\n{HEADER}\n" + "\n".join(lines)


def blocked_status(entry: dict) -> str:
    """What a blocked issue waits on: its open blockers, here or in another repo."""
    refs = [f"#{n}" for n in entry["blocked_by"]] + entry["outside_blockers"]
    return "מחכה ל-" + ", ".join(refs)


def sprint_rows(nodes: list[dict], sprint: str) -> list[tuple[int, str, str]]:
    """The open issues of the sprint, in the order of S-1.3."""
    issues = [
        parse_issue(n)
        for n in nodes
        if n["milestone"] and n["milestone"]["title"] == sprint
    ]
    return [(i.number, i.title, status_he(i.status)) for i in rank(issues)]


def held_rows(nodes: list[dict], picture: dict) -> list[tuple[int, str, str]]:
    """The blocked issues with what they wait on, then those that cost money."""
    titles = {n["number"]: n["title"] for n in nodes}
    rows = [
        (b["number"], titles[b["number"]], blocked_status(b))
        for b in picture["blocked"]
    ]
    rows += [(n, titles[n], "עולה כסף, מחכה לאישור") for n in picture["on_hold"]]
    return rows


def render(repo: str, nodes: list[dict], done: list[dict]) -> str:
    """The four tables as one Markdown text."""
    sprint = current_sprint(nodes)
    done_rows = [
        (i["number"], i["title"], f"Done, {i['closed_at'][:10]}") for i in done
    ]
    sections = [table("מה מוזג לאחרונה", done_rows, repo)]
    if sprint is None:
        sections.append("### מה פתוח בספרינט\n\nאין ספרינט פתוח.")
        picture = {"blocked": [], "on_hold": [], "waiting_dolev": []}
    else:
        picture = state(nodes, sprint, [], lambda pr: {})
        sections.append(
            table(f"מה פתוח בספרינט ({sprint})", sprint_rows(nodes, sprint), repo)
        )
    sections.append(table("מה חסום", held_rows(nodes, picture), repo))
    waiting = [
        (w["number"], w["title"], status_he(w["status"]))
        for w in picture["waiting_dolev"]
    ]
    sections.append(table("מה מחכה לדולב", waiting, repo))
    return "\n\n".join(sections)


def missing_labels(repo: str) -> list[str]:
    """The pipeline labels the repo lacks; none missing means the pipeline is there."""
    names = {label["name"] for label in api_list(f"repos/{repo}/labels?per_page=100")}
    return [name for name in REQUIRED_LABELS if name not in names]


def read(repo: str) -> tuple[list[str], list[dict], list[dict]]:
    """(missing labels, open issues, last merged), or exits 1 with what was not read.

    gh_rest exits with gh's error on a failed call; that exit is turned into a
    message saying which part was not read, instead of a half-built picture.
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
        print(NOT_READ.format(what=what, error=failure.code or ""))
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo", help="owner/name; defaults to the repo of the current directory"
    )
    args = parser.parse_args(argv)

    repo = args.repo or current_repo()
    missing, nodes, done = read(repo)
    if missing:
        print(NO_PIPELINE.format(repo=repo, labels=", ".join(missing)))
        return
    print(render(repo, nodes, done))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
