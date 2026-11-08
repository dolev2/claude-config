"""Ranks the open issues of the current sprint by how much work waits on each one.

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a logged-in
`gh`:

    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/rank_issues.py"                     # the whole sprint
    python "$S/rank_issues.py" --status explore
    python "$S/rank_issues.py" --repo owner/name --json

The repo is the `origin` remote of the current directory, unless --repo is given.
Everything is read through REST (gh_rest.py), because GraphQL is blocked in cloud
sessions (claude-config #138).

The rule is in ../reference/dependencies.md. In short:
an issue's weight is the number of open issues in the sprint that wait on it through
"Blocked by" links, directly or through other issues. Order: the order of --status (the
tier), then `process` and `bug` issues before the rest, then weight, highest first,
then issue number. Blocked issues stay in the list,
because planning ignores blockers; Execute skips them itself.

Issues labelled `costs-money` are on hold until Dolev approves the expense: they leave
the ranking and are listed apart, unless --include-costs-money is given. They still add
weight to what they wait on.

Open issues in the pipeline (past backlog, short of done) that have no milestone are
listed last, apart from the sprint: no scan reaches them, so nothing else would show
them (claude-config #55). They are listed, never ranked.
"""

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field

from gh_rest import current_repo, open_issue_nodes
from sprint_rule import current_sprint

FIRST_KINDS = ["process", "bug"]
NOT_ACTIVE = (None, "backlog", "done")
ON_HOLD_LABEL = "costs-money"


@dataclass
class Issue:
    number: int
    title: str
    status: str | None
    milestone: str | None
    kind: str | None
    costs_money: bool
    open_blockers: list[int]
    blocking: list[int]
    waiting: list[int] = field(default_factory=list)
    outside_blockers: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.open_blockers or self.outside_blockers)


def label_value(labels: Iterable[str], prefix: str) -> str | None:
    for name in labels:
        if name.startswith(prefix):
            return name.removeprefix(prefix)
    return None


def is_local(ref: dict) -> bool:
    """True for a linked issue of the same repo; gh_rest.py marks the others."""
    return not ref.get("repository")


def open_local(refs: dict) -> list[int]:
    """Numbers of the open linked issues of the same repo, sorted."""
    return sorted(
        r["number"] for r in refs["nodes"] if r["state"] == "OPEN" and is_local(r)
    )


def outside_ref(ref: dict) -> str:
    return f"{ref['repository']}#{ref['number']}"


def parse_issue(node: dict) -> Issue:
    """A GraphQL-shaped node as an Issue.

    A blocker of another repo blocks too, but is kept apart as `owner/name#N`: its
    number is not this repo's issue, so it adds no weight and makes no cycle (#164).
    The same goes for what the issue blocks in another repo, which is left out.
    """
    labels = [label["name"] for label in node["labels"]["nodes"]]
    milestone = node["milestone"]
    return Issue(
        number=node["number"],
        title=node["title"],
        status=label_value(labels, "status:"),
        milestone=milestone["title"] if milestone else None,
        kind=next((kind for kind in FIRST_KINDS if kind in labels), None),
        costs_money=ON_HOLD_LABEL in labels,
        open_blockers=open_local(node["blockedBy"]),
        blocking=open_local(node["blocking"]),
        outside_blockers=sorted(
            outside_ref(b)
            for b in node["blockedBy"]["nodes"]
            if b["state"] == "OPEN" and not is_local(b)
        ),
    )


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


def rank(issues: list[Issue], statuses: list[str] | None = None) -> list[Issue]:
    """Filters to the given statuses.

    Orders by tier, then kind (process/bug first), then weight, then number.
    """
    with_waiting(issues)
    picked = [issue for issue in issues if not statuses or issue.status in statuses]

    def key(issue: Issue) -> tuple[int, int, int, int]:
        tier = statuses.index(issue.status) if statuses else 0
        return (tier, 0 if issue.kind else 1, -len(issue.waiting), issue.number)

    return sorted(picked, key=key)


def split_on_hold(ranked: list[Issue]) -> tuple[list[Issue], list[Issue]]:
    """Returns (the ranking without `costs-money` issues, those issues in order)."""
    return (
        [issue for issue in ranked if not issue.costs_money],
        [issue for issue in ranked if issue.costs_money],
    )


def active_without_sprint(nodes: list[dict]) -> list[Issue]:
    """Open pipeline issues (not backlog, not done) with no milestone, by number."""
    issues = [parse_issue(n) for n in nodes if not n["milestone"]]
    return sorted(
        (issue for issue in issues if issue.status not in NOT_ACTIVE),
        key=lambda issue: issue.number,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--status",
        action="append",
        help="status label without the prefix; repeat, in tier order",
    )
    parser.add_argument("--milestone", help="defaults to the current sprint")
    parser.add_argument(
        "--repo", help="owner/name; defaults to the repo of the current directory"
    )
    parser.add_argument(
        "--include-costs-money",
        action="store_true",
        help="keep issues labelled costs-money in the ranking instead of on hold",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    nodes = open_issue_nodes(args.repo or current_repo())
    sprint = args.milestone or current_sprint(nodes)
    if sprint is None:
        sys.exit("No open milestone has open issues.")
    issues = [
        parse_issue(n)
        for n in nodes
        if n["milestone"] and n["milestone"]["title"] == sprint
    ]
    ranked = rank(issues, args.status)
    on_hold: list[Issue] = []
    if not args.include_costs_money:
        ranked, on_hold = split_on_hold(ranked)
    no_sprint = active_without_sprint(nodes)

    if args.json:
        rows = [
            {
                "number": i.number,
                "title": i.title,
                "status": i.status,
                "kind": i.kind,
                "costs_money": i.costs_money,
                "waiting": i.waiting,
                "open_blockers": i.open_blockers,
                "outside_blockers": i.outside_blockers,
            }
            for i in ranked
        ]
        payload = {
            "sprint": sprint,
            "issues": rows,
            "on_hold": [i.number for i in on_hold],
            "no_sprint": [i.number for i in no_sprint],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print_ranking(sprint, ranked, on_hold, no_sprint)


def print_ranking(
    sprint: str, ranked: list[Issue], on_hold: list[Issue], no_sprint: list[Issue]
) -> None:
    """The ranking as text: the sprint, one row per issue, then the lists apart."""
    print(f"Sprint: {sprint}")
    if not ranked:
        print("(no matching issues)")
    for i in ranked:
        blockers = [f"#{n}" for n in i.open_blockers] + i.outside_blockers
        blocked = f"  BLOCKED by {', '.join(blockers)}" if i.blocked else ""
        print(
            f"#{i.number:<4} {len(i.waiting):>2} waiting  "
            f"{i.status or '-':<24} {i.kind or '-':<7} "
            f"{i.title}{blocked}"
        )
    if on_hold:
        held = ", ".join(f"#{i.number} {i.title}" for i in on_hold)
        print(f"On hold, {ON_HOLD_LABEL}: {held}")
    if no_sprint:
        listed = ", ".join(f"#{i.number} {i.title} ({i.status})" for i in no_sprint)
        print(f"Active, no sprint: {listed}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
