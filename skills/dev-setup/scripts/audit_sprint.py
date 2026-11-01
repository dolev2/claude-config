"""Checks the "Blocked by" links of the whole sprint, and reports what looks off.

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a logged-in
`gh`:

    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/audit_sprint.py"                    # one line per finding
    python "$S/audit_sprint.py" --json             # the digest, for a full review

The rule is in ../reference/dependencies.md. The ranking of
rank_issues.py is only as good as the links behind it; these are the findings a script
can see without judging the work itself:

    LINE-MISMATCH #N   the "תלוי ב:" line and the links list different issues
    OUTSIDE #N -> #B   an open blocker that is not an open issue of this sprint
    CYCLE #A #B ...    issues that block each other, so none of them can move
    MENTION #N -> #B   the goal or context names a sprint issue, with no link either way
                       (a parent naming its sub-issues, or the other way, is not one)
    OVERLAP #A #B      both plans list the same files and no link joins them;
                       "merge-candidate" when neither has a linked PR yet

A MENTION or an OVERLAP is a signal, not a proposal: whether it is a dependency, a
collision risk or a merge is Claude's call in dev-next, and Dolev's to approve. The exit
code is always 0, because this is advice, not a gate.
"""

import argparse
import itertools
import json
import sys
from dataclasses import dataclass

from issue_body import (
    CONTEXT_HEADINGS,
    GOAL_HEADINGS,
    dependency_line,
    mentioned,
    plan_files,
    section,
    sections,
)
from rank_issues import current_repo, current_sprint, fetch_nodes, parse_issue

QUERY = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    issues(states: OPEN, first: 100, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        title
        body
        labels(first: 30) { nodes { name } }
        milestone { title number state }
        blockedBy(first: 50) { nodes { number state } }
        blocking(first: 50) { nodes { number state } }
        closedByPullRequestsReferences(first: 1) { totalCount }
        parent { number }
        subIssues(first: 50) { nodes { number } }
      }
    }
  }
}
"""
SHARED_DOCS = {"README.md", "CLAUDE.md"}


@dataclass
class Finding:
    code: str
    numbers: list[int]
    detail: str = ""

    def line(self) -> str:
        if self.code in ("OUTSIDE", "MENTION"):
            refs = f"#{self.numbers[0]} -> #{self.numbers[1]}"
        else:
            refs = " ".join(f"#{n}" for n in self.numbers)
        return f"{self.code} {refs}{': ' + self.detail if self.detail else ''}"


@dataclass
class SprintIssue:
    number: int
    title: str
    status: str | None
    owner: str | None
    goal: str
    context: str
    line: list[int] | None
    files: set[str]
    linked: list[int]
    open_blockers: list[int]
    has_pr: bool
    family: set[int]


def sprint_issue(node: dict) -> SprintIssue:
    parts = sections(node.get("body") or "")
    issue = parse_issue(node)
    context = section(parts, CONTEXT_HEADINGS)
    return SprintIssue(
        number=issue.number,
        title=issue.title,
        status=issue.status,
        owner=issue.owner,
        goal=section(parts, GOAL_HEADINGS).strip(),
        context=context,
        line=dependency_line(context),
        files=plan_files(parts.get("plan", "")),
        linked=sorted(b["number"] for b in node["blockedBy"]["nodes"]),
        open_blockers=issue.open_blockers,
        has_pr=node["closedByPullRequestsReferences"]["totalCount"] > 0,
        family=family(node),
    )


def family(node: dict) -> set[int]:
    """The parent and the sub-issues: an umbrella names them without waiting on them."""
    parent = node.get("parent")
    subs = (node.get("subIssues") or {}).get("nodes", [])
    return {s["number"] for s in subs} | ({parent["number"]} if parent else set())


def line_mismatches(issues: list[SprintIssue]) -> list[Finding]:
    return [
        Finding(
            "LINE-MISMATCH",
            [i.number],
            f"line {refs(i.line)}, links {refs(i.linked)}",
        )
        for i in issues
        if i.line is not None and i.line != i.linked
    ]


def outside_blockers(issues: list[SprintIssue]) -> list[Finding]:
    in_sprint = {i.number for i in issues}
    return [
        Finding("OUTSIDE", [i.number, b])
        for i in issues
        for b in i.open_blockers
        if b not in in_sprint
    ]


def cycles(issues: list[SprintIssue]) -> list[Finding]:
    """One finding per group of issues that block each other, directly or not."""
    in_sprint = {i.number for i in issues}
    edges = {i.number: [b for b in i.open_blockers if b in in_sprint] for i in issues}
    reach = {n: reachable(n, edges) for n in edges}
    groups = {
        tuple(sorted(m for m in reach[n] if n in reach[m]) or [n])
        for n in edges
        if n in reach[n]
    }
    return [Finding("CYCLE", list(group)) for group in sorted(groups)]


def reachable(start: int, edges: dict[int, list[int]]) -> set[int]:
    seen: set[int] = set()
    stack = list(edges[start])
    while stack:
        n = stack.pop()
        if n not in seen:
            seen.add(n)
            stack.extend(edges[n])
    return seen


def mentions(issues: list[SprintIssue]) -> list[Finding]:
    """Sprint issues named in the goal or context, outside the dependency line."""
    by_number = {i.number: i for i in issues}
    found = []
    for issue in issues:
        named = sorted(mentioned(issue.goal + "\n" + issue.context))
        for other in named:
            if other in by_number and other not in issue.family | {issue.number}:
                if not are_linked(issue, by_number[other]):
                    found.append(Finding("MENTION", [issue.number, other]))
    return found


def overlaps(issues: list[SprintIssue]) -> list[Finding]:
    found = []
    for a, b in itertools.combinations(issues, 2):
        shared = sorted(f for f in a.files & b.files if not is_shared_doc(f))
        if shared and not are_linked(a, b):
            merge = "" if a.has_pr or b.has_pr else "  merge-candidate"
            found.append(
                Finding("OVERLAP", [a.number, b.number], ", ".join(shared) + merge)
            )
    return found


def is_shared_doc(path: str) -> bool:
    """README.md and CLAUDE.md: nearly every plan updates them, so they say nothing."""
    return path.rsplit("/", 1)[-1] in SHARED_DOCS


def are_linked(a: SprintIssue, b: SprintIssue) -> bool:
    return b.number in a.linked or a.number in b.linked


def refs(numbers: list[int]) -> str:
    return ", ".join(f"#{n}" for n in numbers) or "none"


def audit(issues: list[SprintIssue]) -> list[Finding]:
    """Every finding for the given sprint issues, in a fixed order."""
    return [
        *line_mismatches(issues),
        *outside_blockers(issues),
        *cycles(issues),
        *mentions(issues),
        *overlaps(issues),
    ]


def digest(sprint: str, issues: list[SprintIssue], findings: list[Finding]) -> dict:
    """The sprint as one JSON object: what a full review reads in one pass."""
    return {
        "sprint": sprint,
        "issues": [
            {
                "number": i.number,
                "title": i.title,
                "status": i.status,
                "owner": i.owner,
                "goal": i.goal,
                "files": sorted(i.files),
                "blocked_by": i.open_blockers,
                "has_pr": i.has_pr,
            }
            for i in issues
        ],
        "findings": [f.line() for f in findings],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--milestone", help="defaults to the current sprint")
    parser.add_argument(
        "--repo", help="owner/name; defaults to the repo of the current directory"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    nodes = fetch_nodes(args.repo or current_repo(), QUERY)
    sprint = args.milestone or current_sprint(nodes)
    if sprint is None:
        sys.exit("No open milestone has open issues.")
    issues = [
        sprint_issue(n)
        for n in nodes
        if n["milestone"] and n["milestone"]["title"] == sprint
    ]
    findings = audit(issues)

    if args.json:
        print(
            json.dumps(digest(sprint, issues, findings), ensure_ascii=False, indent=2)
        )
        return
    print(f"Sprint: {sprint}")
    for finding in findings:
        print(finding.line())
    if not findings:
        print("(no findings)")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
