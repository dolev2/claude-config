"""Ranks the open issues of the current sprint by how much work waits on each one.

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a logged-in
`gh`:

    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/rank_issues.py"                     # the whole sprint
    python "$S/rank_issues.py" --owner claude --status explore
    python "$S/rank_issues.py" --repo owner/name --json

The repo is the one `gh repo view` sees from the current directory, unless --repo is
given.

The rule is in ../reference/pipeline.md, section "סדר בתוך הספרינט". In short:
an issue's weight is the number of open issues in the sprint that wait on it through
"Blocked by" links, directly or through other issues. Order: the order of --status (the
tier), then weight, highest first, then issue number. Blocked issues stay in the list,
because planning ignores blockers; Execute skips them itself.
"""

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field

QUERY = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    issues(states: OPEN, first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        labels(first: 30) { nodes { name } }
        milestone { title number state }
        blockedBy(first: 50) { nodes { number state } }
        blocking(first: 50) { nodes { number state } }
      }
    }
  }
}
"""


@dataclass
class Issue:
    number: int
    title: str
    status: str | None
    owner: str | None
    milestone: str | None
    open_blockers: list[int]
    blocking: list[int]
    waiting: list[int] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.open_blockers)


def label_value(labels: Iterable[str], prefix: str) -> str | None:
    for name in labels:
        if name.startswith(prefix):
            return name.removeprefix(prefix)
    return None


def parse_issue(node: dict) -> Issue:
    labels = [label["name"] for label in node["labels"]["nodes"]]
    milestone = node["milestone"]
    return Issue(
        number=node["number"],
        title=node["title"],
        status=label_value(labels, "status:"),
        owner=label_value(labels, "owner:"),
        milestone=milestone["title"] if milestone else None,
        open_blockers=sorted(
            b["number"] for b in node["blockedBy"]["nodes"] if b["state"] == "OPEN"
        ),
        blocking=sorted(
            b["number"] for b in node["blocking"]["nodes"] if b["state"] == "OPEN"
        ),
    )


def current_sprint(nodes: list[dict]) -> str | None:
    """The open milestone with the lowest number that still has open issues."""
    open_milestones = {
        n["milestone"]["number"]: n["milestone"]["title"]
        for n in nodes
        if n["milestone"] and n["milestone"]["state"] == "OPEN"
    }
    return open_milestones[min(open_milestones)] if open_milestones else None


def with_waiting(issues: list[Issue]) -> list[Issue]:
    """Fills in `waiting`: every sprint issue that waits on this one, directly or not.

    Only edges between the given issues count, so work outside the sprint adds no
    weight.
    """
    by_number = {issue.number: issue for issue in issues}
    for issue in issues:
        seen: set[int] = set()
        stack = [n for n in issue.blocking if n in by_number]
        while stack:
            n = stack.pop()
            if n in seen or n == issue.number:
                continue
            seen.add(n)
            stack.extend(m for m in by_number[n].blocking if m in by_number)
        issue.waiting = sorted(seen)
    return issues


def rank(
    issues: list[Issue], statuses: list[str] | None = None, owner: str | None = None
) -> list[Issue]:
    """Filters to the given owner and statuses, then orders by tier, weight, number."""
    with_waiting(issues)
    picked = [
        issue
        for issue in issues
        if (owner is None or issue.owner == owner)
        and (not statuses or issue.status in statuses)
    ]

    def key(issue: Issue) -> tuple[int, int, int]:
        tier = statuses.index(issue.status) if statuses else 0
        return (tier, -len(issue.waiting), issue.number)

    return sorted(picked, key=key)


def current_repo() -> str:
    """owner/name of the repo `gh` resolves from the current directory."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        sys.exit(
            "Not inside a GitHub repo that gh can see; pass --repo owner/name.\n"
            + result.stderr
        )
    return result.stdout.strip()


def fetch_nodes(repo: str) -> list[dict]:
    owner, name = repo.split("/", 1)
    nodes: list[dict] = []
    after = None
    while True:
        args = [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={QUERY}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
        ]
        if after:
            args += ["-F", f"after={after}"]
        result = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8", check=False
        )
        if result.returncode != 0:
            sys.exit(f"gh api graphql failed:\n{result.stderr}")
        page = json.loads(result.stdout)["data"]["repository"]["issues"]
        nodes += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return nodes
        after = page["pageInfo"]["endCursor"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--status",
        action="append",
        help="status label without the prefix; repeat, in tier order",
    )
    parser.add_argument("--owner", help="owner label without the prefix, e.g. claude")
    parser.add_argument("--milestone", help="defaults to the current sprint")
    parser.add_argument(
        "--repo", help="owner/name; defaults to the repo of the current directory"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    nodes = fetch_nodes(args.repo or current_repo())
    sprint = args.milestone or current_sprint(nodes)
    if sprint is None:
        sys.exit("No open milestone has open issues.")
    issues = [
        parse_issue(n)
        for n in nodes
        if n["milestone"] and n["milestone"]["title"] == sprint
    ]
    ranked = rank(issues, args.status, args.owner)

    if args.json:
        rows = [
            {
                "number": i.number,
                "title": i.title,
                "status": i.status,
                "owner": i.owner,
                "waiting": i.waiting,
                "open_blockers": i.open_blockers,
            }
            for i in ranked
        ]
        print(
            json.dumps({"sprint": sprint, "issues": rows}, ensure_ascii=False, indent=2)
        )
        return

    print(f"Sprint: {sprint}")
    if not ranked:
        print("(no matching issues)")
    for i in ranked:
        blocked = (
            f"  BLOCKED by {', '.join(f'#{n}' for n in i.open_blockers)}"
            if i.blocked
            else ""
        )
        print(
            f"#{i.number:<4} {len(i.waiting):>2} waiting  "
            f"{i.status or '-':<18} {i.owner or '-':<7} {i.title}{blocked}"
        )


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
