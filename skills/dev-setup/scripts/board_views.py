"""Gives a repo's Project board the pipeline's two views: "ספרינט נוכחי" and "הכל".

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a `gh` logged
in with the `project` scope:

    python "$HOME/.claude/skills/dev-setup/scripts/board_views.py" --dry-run
    python "$HOME/.claude/skills/dev-setup/scripts/board_views.py"

- "ספרינט נוכחי": a board split into Status columns, filtered to `milestone:"<sprint>"`.
- "הכל": a table of every item.

The sprint defaults to the current one, by the pipeline's shared rule (sprint_rule.py:
open issues, PRs not counted), or, in a repo with no open issues yet, the
lowest-numbered open milestone.

The repo, its milestones and its issues are read over REST (gh_rest.py), which a cloud
session allows. The board itself is read and written over GraphQL, because Projects V2
has no REST API for views; a cloud session blocks that part (claude-config #140).

A view that already carries one of the two names is left as it is, so a second run
changes nothing. The board's untouched default view ("View 1", a table with no filter)
becomes the sprint view, so it stays the first tab. Nothing is deleted, and views with
other names are not touched. Moving the filter to the next sprint is the board sync's
job (reference/setup.md).
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

import gh_rest
import sprint_rule

SPRINT_VIEW = "ספרינט נוכחי"
ALL_VIEW = "הכל"
SPRINT_FIELDS = ["Title", "Assignees", "Status"]
ALL_FIELDS = [
    "Title",
    "Assignees",
    "Status",
    "Linked pull requests",
    "Milestone",
    "Sub-issues progress",
]
DEFAULT_VIEW = re.compile(r"^View \d+$")

BOARD_QUERY = """query($owner:String!,$number:Int!){
  user(login:$owner){projectV2(number:$number){
    id title
    fields(first:50){nodes{... on ProjectV2FieldCommon{id name}}}
    views(first:50){nodes{
      id name layout filter
      verticalGroupByFields(first:5){nodes{... on ProjectV2FieldCommon{name}}}
    }}
  }}
}"""
CREATE = """mutation(
  $project:ID!,$name:String!,$layout:ProjectV2ViewLayout!,$fields:[ID!]
){
  createProjectV2View(input:{
    projectId:$project,name:$name,layout:$layout,
    configuration:{visibleFieldIds:$fields}
  }){projectV2View{id}}
}"""
UPDATE = """mutation(
  $view:ID!,$name:String,$layout:ProjectV2ViewLayout,$filter:String,$fields:[ID!]
){
  updateProjectV2View(input:{
    viewId:$view,name:$name,layout:$layout,filter:$filter,
    configuration:{visibleFieldIds:$fields}
  }){projectV2View{id}}
}"""


def run(*args: str) -> tuple[int, str]:
    p = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return p.returncode, (p.stdout or p.stderr).strip()


def graphql(query: str, **variables: object) -> dict:
    """One GraphQL call, sent through a file so lists and Hebrew pass intact."""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".json", encoding="utf-8", delete=False
    ) as f:
        json.dump({"query": query, "variables": variables}, f, ensure_ascii=False)
    try:
        code, out = run("gh", "api", "graphql", "--input", f.name)
    finally:
        os.unlink(f.name)
    if code != 0:
        sys.exit(f"GraphQL call failed: {out}")
    return json.loads(out)["data"]


def open_milestones(repo: str) -> list[dict]:
    """The repo's open milestones over REST, lowest number first."""
    items = gh_rest.api_list(f"repos/{repo}/milestones?state=open&per_page=100")
    return sorted(items, key=lambda m: m["number"])


def pick_sprint(current: str | None, milestones: list[dict]) -> str | None:
    """`current` (the shared rule's sprint), or the first open milestone without one.

    `milestones` is sorted by number. None when there is neither.
    """
    if current:
        return current
    return milestones[0]["title"] if milestones else None


def plan(views: list[dict], field_ids: dict[str, str], sprint: str) -> list[tuple]:
    """The mutations to send, as (query, variables, description) tuples."""
    names = {v["name"] for v in views}
    sprint_vars = {
        "name": SPRINT_VIEW,
        "layout": "BOARD_LAYOUT",
        "filter": f'milestone:"{sprint}"',
        "fields": [field_ids[f] for f in SPRINT_FIELDS],
    }
    steps = []
    if SPRINT_VIEW not in names:
        default = next(
            (
                v
                for v in views
                if DEFAULT_VIEW.match(v["name"])
                and v["layout"] == "TABLE_LAYOUT"
                and not v["filter"]
            ),
            None,
        )
        if default:
            steps.append(
                (
                    UPDATE,
                    {"view": default["id"], **sprint_vars},
                    f'"{default["name"]}" becomes "{SPRINT_VIEW}"',
                )
            )
        else:
            steps.append(
                (
                    CREATE,
                    {
                        "name": SPRINT_VIEW,
                        "layout": "BOARD_LAYOUT",
                        "fields": sprint_vars["fields"],
                    },
                    f'create "{SPRINT_VIEW}"',
                )
            )
            steps.append(
                (
                    UPDATE,
                    {"filter": sprint_vars["filter"]},
                    f'filter "{SPRINT_VIEW}" to {sprint_vars["filter"]}',
                )
            )
    if ALL_VIEW not in names:
        steps.append(
            (
                CREATE,
                {
                    "name": ALL_VIEW,
                    "layout": "TABLE_LAYOUT",
                    "fields": [field_ids[f] for f in ALL_FIELDS],
                },
                f'create "{ALL_VIEW}"',
            )
        )
    return steps


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo", help="owner/name; defaults to the repo of the current directory"
    )
    parser.add_argument(
        "--number",
        type=int,
        help="the board's number; defaults to the PROJECT_NUMBER variable",
    )
    parser.add_argument(
        "--sprint",
        help="the milestone the sprint view shows; defaults to the current sprint",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would change, change nothing"
    )
    args = parser.parse_args(argv)

    repo = args.repo or gh_rest.current_repo()
    owner = repo.split("/")[0]
    number = args.number
    if number is None:
        code, out = run("gh", "variable", "get", "PROJECT_NUMBER", "--repo", repo)
        if code != 0 or not out.isdigit():
            sys.exit(f"{repo} has no PROJECT_NUMBER variable; pass --number.")
        number = int(out)

    milestones = open_milestones(repo)
    sprint = args.sprint
    if not sprint:
        issues = gh_rest.api_list(f"repos/{repo}/issues?state=open&per_page=100")
        sprint = pick_sprint(sprint_rule.current_sprint(issues), milestones)
    if not sprint:
        sys.exit(f"{repo} has no open milestone; create the sprints first.")
    if sprint not in {m["title"] for m in milestones}:
        # A filter on a missing milestone shows an empty board without any error.
        sys.exit(f'"{sprint}" is not an open milestone of {repo}.')

    project = graphql(BOARD_QUERY, owner=owner, number=number)["user"]["projectV2"]
    if not project:
        sys.exit(
            f"Board {number} of {owner} not found (does gh have the project scope?)."
        )
    field_ids = {f["name"]: f["id"] for f in project["fields"]["nodes"] if f}
    missing = [
        f for f in dict.fromkeys(SPRINT_FIELDS + ALL_FIELDS) if f not in field_ids
    ]
    if missing:
        sys.exit(f"Board {number} has no field {', '.join(missing)}.")

    steps = plan(project["views"]["nodes"], field_ids, sprint)
    print(f'Board {number} ({project["title"]}), sprint "{sprint}"')
    if not steps:
        print("Both views are there; nothing to do.")
    created = None
    for query, variables, description in steps:
        print(("would: " if args.dry_run else "") + description)
        if args.dry_run:
            continue
        if query is CREATE:
            created = graphql(query, project=project["id"], **variables)[
                "createProjectV2View"
            ]["projectV2View"]["id"]
        else:
            graphql(query, **{"view": created, **variables})
    if args.dry_run or not steps:
        return

    views = graphql(BOARD_QUERY, owner=owner, number=number)["user"]["projectV2"][
        "views"
    ]["nodes"]
    for v in views:
        print(f"  {v['name']}: {v['layout']}, filter {v['filter'] or '-'}")
        columns = v["verticalGroupByFields"]["nodes"]
        if v["name"] == SPRINT_VIEW and not columns:
            print(
                f'  -> open "{SPRINT_VIEW}" in the board and choose '
                '"Column by: Status"; the API cannot set it.'
            )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
