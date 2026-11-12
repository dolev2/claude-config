"""Ranks the open issues of the current sprint: a topic is finished before the next.

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a logged-in
`gh`:

    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/rank_issues.py"                     # the whole sprint
    python "$S/rank_issues.py" --status explore
    python "$S/rank_issues.py" --repo owner/name --json

The repo is the `origin` remote of the current directory, unless --repo is given.
Everything is read through REST (gh_rest.py), because GraphQL is blocked in cloud
sessions (claude-config #138).

The rule is in ../reference/dependencies.md (S-1.3, claude-config #295). In short:
an issue's weight is the number of open issues in the sprint that wait on it through
"Blocked by" links, directly or through other issues. Order: a repair
(`needs-repair`, when it is in --status) first, then every `bug` before any new task,
then the order of --status (the tier), then `process` issues before the rest, then the
sub-issues of an umbrella that has started, then weight, LOWEST first, then issue
number. An umbrella has started when one of its sub-issues is closed, or open in
`in-review` or `needs-repair`; the umbrella may sit in any milestone. Each row carries
the reason it stands where it does. Blocked issues stay in
the list, marked `BLOCKED by`: they still carry weight, and each skill skips them
itself, in planning and in Execute alike (claude-config #253). An umbrella, an issue
with an open sub-issue, stays too, marked `UMBRELLA, open sub-issues`: it is not worked
on itself until they close, and dev-code skips it (claude-config #250).

Issues labelled `costs-money` are on hold until Dolev approves the expense: they leave
the ranking and are listed apart, unless --include-costs-money is given. Issues labelled
`paused` are paused by Dolev by hand: they leave the ranking too, always, and are listed
on their own line. Both still add weight to what they wait on, and what waits on a
paused issue shows `(paused)` next to its number.

Open issues in the pipeline (past backlog, short of done) that have no milestone are
listed last, apart from the sprint: no scan reaches them, so nothing else would show
them (claude-config #55). They are listed, never ranked.
"""

import argparse
import json
import sys
from collections.abc import Iterable, Sequence, Set
from dataclasses import dataclass, field

from gh_rest import current_repo, open_issue_nodes
from sprint_rule import current_sprint

# An issue with both labels is a bug: the bug-first rule wins (#202).
FIRST_KINDS = ["bug", "process"]
REPAIR = "needs-repair"
NOT_ACTIVE = (None, "backlog", "done")
ON_HOLD_LABEL = "costs-money"
PAUSED_LABEL = "paused"
# A sub-issue in one of these has code written: its umbrella has started (#295).
STARTED_STATUSES = ("in-review", "needs-repair")


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
    open_subs: list[str] = field(default_factory=list)
    paused: bool = False
    umbrella_of: int | None = None

    @property
    def blocked(self) -> bool:
        return bool(self.open_blockers or self.outside_blockers)

    @property
    def umbrella(self) -> bool:
        """An issue with an open sub-issue is not worked on itself (dependencies.md).

        Once every sub-issue is closed, the issue is ordinary work again (#211).
        """
        return bool(self.open_subs)

    @property
    def reason(self) -> str:
        """Why the issue stands where it is: bug, process, umbrella, fewest-waiting."""
        if self.kind:
            return self.kind
        return "umbrella" if self.umbrella_of else "fewest-waiting"


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


def open_subs(node: dict) -> list[str]:
    """The issue's open sub-issues: #N, or owner/name#N for another repo."""
    subs = (node.get("subIssues") or {}).get("nodes") or []
    return [
        f"#{s['number']}" if is_local(s) else outside_ref(s)
        for s in subs
        if s.get("state") == "OPEN"
    ]


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
        paused=PAUSED_LABEL in labels,
        open_blockers=open_local(node["blockedBy"]),
        blocking=open_local(node["blocking"]),
        outside_blockers=sorted(
            outside_ref(b)
            for b in node["blockedBy"]["nodes"]
            if b["state"] == "OPEN" and not is_local(b)
        ),
        open_subs=open_subs(node),
    )


def started_umbrellas(nodes: list[dict]) -> dict[int, int]:
    """Each open sub-issue of a started umbrella, mapped to that umbrella's number.

    `nodes` are all the open issues of the repo, not only the sprint's: the umbrella
    may sit in another milestone. Started: a sub-issue is closed (not planned too), or
    open in `in-review` or `needs-repair`. A sub-issue of another repo neither starts
    an umbrella nor is moved up; only the direct umbrella counts.
    """
    status = {
        n["number"]: label_value((x["name"] for x in n["labels"]["nodes"]), "status:")
        for n in nodes
    }
    found: dict[int, int] = {}
    for umbrella in nodes:
        subs = [
            s
            for s in (umbrella.get("subIssues") or {}).get("nodes") or []
            if is_local(s)
        ]
        started = any(
            s["state"] != "OPEN" or status.get(s["number"]) in STARTED_STATUSES
            for s in subs
        )
        if started:
            for sub in subs:
                if sub["state"] == "OPEN":
                    found.setdefault(sub["number"], umbrella["number"])
    return found


def with_started_umbrellas(issues: list[Issue], nodes: list[dict]) -> list[Issue]:
    """Fills in `umbrella_of` from all the open issues of the repo, `nodes`."""
    started = started_umbrellas(nodes)
    for issue in issues:
        issue.umbrella_of = started.get(issue.number)
    return issues


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
    """Filters to the given statuses, and orders them.

    The key: a repair first (it is no new task, and its PR is aging), then a bug
    before any new task, then the tier, then `process`, then a sub-issue of a started
    umbrella (`umbrella_of`, filled by with_started_umbrellas), then weight, lowest
    first, then number (S-1.3). A blocker may so stand below what it blocks: the pick
    is always the first row that is not blocked.
    """
    with_waiting(issues)
    picked = [issue for issue in issues if not statuses or issue.status in statuses]

    def key(issue: Issue) -> tuple[int, int, int, int, int, int, int]:
        tier = statuses.index(issue.status) if statuses else 0
        repair_first = bool(statuses) and issue.status == REPAIR
        return (
            0 if repair_first else 1,
            0 if issue.kind == "bug" else 1,
            tier,
            0 if issue.kind == "process" else 1,
            0 if issue.umbrella_of else 1,
            len(issue.waiting),
            issue.number,
        )

    return sorted(picked, key=key)


def split_on_hold(
    ranked: list[Issue], include_costs_money: bool = False
) -> tuple[list[Issue], list[Issue], list[Issue]]:
    """(the ranking, the `costs-money` issues, the `paused` issues), each in order.

    A paused issue is out of the ranking even with `include_costs_money`: the pause is
    Dolev's decision, not a check of an expense. An issue with both labels is paused.
    """
    paused = [issue for issue in ranked if issue.paused]
    rest = [issue for issue in ranked if not issue.paused]
    if include_costs_money:
        return rest, [], paused
    return (
        [issue for issue in rest if not issue.costs_money],
        [issue for issue in rest if issue.costs_money],
        paused,
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
    ranked = rank(with_started_umbrellas(issues, nodes), args.status)
    ranked, on_hold, paused = split_on_hold(ranked, args.include_costs_money)
    no_sprint = active_without_sprint(nodes)
    paused_numbers = {i.number for i in map(parse_issue, nodes) if i.paused}

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
                "open_subs": i.open_subs,
                "paused_blockers": [n for n in i.open_blockers if n in paused_numbers],
                "reason": i.reason,
                "umbrella_of": i.umbrella_of,
            }
            for i in ranked
        ]
        payload = {
            "sprint": sprint,
            "issues": rows,
            "on_hold": [i.number for i in on_hold],
            "paused": [i.number for i in paused],
            "no_sprint": [i.number for i in no_sprint],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print_ranking(sprint, ranked, on_hold, no_sprint, paused, paused_numbers)


def blocker_refs(issue: Issue, paused_numbers: set[int]) -> list[str]:
    """The open blockers as #N, `(paused)` after a paused one, then other repos'."""
    local = [
        f"#{n} (paused)" if n in paused_numbers else f"#{n}"
        for n in issue.open_blockers
    ]
    return local + issue.outside_blockers


def print_ranking(
    sprint: str,
    ranked: list[Issue],
    on_hold: list[Issue],
    no_sprint: list[Issue],
    paused: Sequence[Issue] = (),
    paused_numbers: Set[int] = frozenset(),
) -> None:
    """The ranking as text: the sprint, one row per issue, then the lists apart."""
    print(f"Sprint: {sprint}")
    if not ranked:
        print("(no matching issues)")
    for i in ranked:
        blockers = blocker_refs(i, paused_numbers)
        blocked = f"  BLOCKED by {', '.join(blockers)}" if i.blocked else ""
        started = f"  FROM STARTED UMBRELLA #{i.umbrella_of}" if i.umbrella_of else ""
        umbrella = (
            f"  UMBRELLA, open sub-issues {', '.join(i.open_subs)}"
            if i.umbrella
            else ""
        )
        print(
            f"#{i.number:<4} {len(i.waiting):>2} waiting  "
            f"{i.status or '-':<24} {i.kind or '-':<7} "
            f"{i.title}{started}{blocked}{umbrella}"
        )
    if on_hold:
        held = ", ".join(f"#{i.number} {i.title}" for i in on_hold)
        print(f"On hold, {ON_HOLD_LABEL}: {held}")
    if paused:
        held = ", ".join(f"#{i.number} {i.title}" for i in paused)
        print(f"Paused by Dolev: {held}")
    if no_sprint:
        listed = ", ".join(f"#{i.number} {i.title} ({i.status})" for i in no_sprint)
        print(f"Active, no sprint: {listed}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
