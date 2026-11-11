"""The approved proposals of a sprint and the stage of each, for sprint_state.py.

S-2.14 (claude-config #296): a backlog proposal Dolev put in the sprint's milestone is
approved for a spec, with no new label (docs/decisions/296-sprint-milestone-approves-
proposal.md). The orchestrator sends it a spec child before any other child, one at a
time, since every spec child writes the repo's one spec file and its table of contents.

The stage of a proposal is read from the spec PRs that reference it (`claude/spec-*`,
`Refs #N`), which sprint_github.spec_prs() reads; here they are passed in, so the logic
is tested without a network:

    waiting    no open or merged spec PR, and no child: it gets a spec child
    writing    a child is working on it (--claimed)
    questions  an open spec PR whose "שאלות פתוחות" section has an unticked box
    review     an open spec PR with no open question: a merge question
    breakdown  a merged spec PR, and the proposal is still open: the breakdown waits
               for Dolev's approval
"""

import re
from collections.abc import Callable

from issue_body import section, sections
from rank_issues import parse_issue
from sprint_github import SPEC_BRANCH

BACKLOG = "backlog"
SPEC_PROMPT = "תכתוב אפיון ל-#{}"
QUESTION_HEADINGS = ("שאלות פתוחות", "open questions")
UNTICKED = re.compile(r"^\s*[-*+]\s*\[\s\]", re.MULTILINE)


def is_proposal(node: dict, sprint: str) -> bool:
    """An approved proposal: open, `status:backlog`, in the sprint's milestone.

    Not a bug (it points at the part it breaks), not an umbrella (its sub-issues are
    the work, as #221 is), and not costs-money. An issue the planning gate sent back
    to the backlog with its milestone kept is one too (Dolev's answer on #296).
    """
    issue = parse_issue(node)
    return (
        issue.milestone == sprint
        and issue.status == BACKLOG
        and issue.kind != "bug"
        and not issue.umbrella
        and not issue.costs_money
        and not issue.paused
    )


def has_open_question(pr_body: str) -> bool:
    """True when the PR body's "שאלות פתוחות" section has an unticked box."""
    return bool(UNTICKED.search(section(sections(pr_body), QUESTION_HEADINGS)))


def stage(prs: list[dict], is_claimed: bool) -> tuple[str, dict | None]:
    """(stage, the spec PR it is read from or None), from the proposal's spec PRs.

    `prs` are [{number, state, branch, body, headSha}], state "open", "merged" or
    "closed". A PR closed without a merge counts for nothing: the proposal waits again.
    """
    specs = [pr for pr in prs if pr["branch"].startswith(SPEC_BRANCH)]
    open_pr = next((pr for pr in specs if pr["state"] == "open"), None)
    merged = next((pr for pr in specs if pr["state"] == "merged"), None)
    if is_claimed:
        return "writing", open_pr
    if open_pr:
        return (
            "questions" if has_open_question(open_pr["body"]) else "review"
        ), open_pr
    if merged:
        return "breakdown", merged
    return "waiting", None


def proposals(
    nodes: list[dict],
    sprint: str,
    claimed: list[int],
    spec_prs_of: Callable[[int], list[dict]],
) -> list[dict]:
    """Every approved proposal of the sprint, by number: {number, title, stage, pr}."""
    found = []
    for node in sorted(nodes, key=lambda n: n["number"]):
        if not is_proposal(node, sprint):
            continue
        name, pr = stage(spec_prs_of(node["number"]), node["number"] in claimed)
        found.append(
            {
                "number": node["number"],
                "title": node["title"],
                "stage": name,
                "pr": pr["number"] if pr else None,
                "head_sha": pr["headSha"] if pr else None,
            }
        )
    return found


def spec_split(found: list[dict], spec_file: str) -> tuple[list[dict], list[dict]]:
    """(dispatch, held_by_overlap) of the proposals waiting for a spec child.

    One spec child at a time: two would write the same file and table of contents and
    meet in a rebase conflict. While one is writing, every waiting one is held.
    """
    writing = [p["number"] for p in found if p["stage"] == "writing"]
    dispatch, held = [], []
    for proposal in (p for p in found if p["stage"] == "waiting"):
        if writing:
            held.append(
                {"number": proposal["number"], "with": writing, "files": [spec_file]}
            )
            continue
        writing = [proposal["number"]]
        dispatch.append(
            {
                "number": proposal["number"],
                "title": proposal["title"],
                "status": "spec",
                "kind": None,
                "waiting": [],
                "prompt": SPEC_PROMPT.format(proposal["number"]),
            }
        )
    return dispatch, held


def spec_merge_queue(
    found: list[dict], spec_file: str, status_of: Callable[[dict], dict]
) -> list[dict]:
    """The merge_queue rows of spec PRs ready for review, like a task's PR.

    `overlaps` names the other proposals whose spec is in flight (a child writing it,
    or an open spec PR): they write the same file. A code task never counts, since its
    PR changes only the status line of its own part (S-2.14).
    """
    in_flight = [p for p in found if p["stage"] in ("writing", "questions", "review")]
    return [
        {
            "number": p["number"],
            "pr": p["pr"],
            "head_sha": p["head_sha"],
            "kind": "spec",
        }
        | status_of({"number": p["pr"], "headSha": p["head_sha"]})
        | {
            "overlaps": [
                {"number": other["number"], "files": [spec_file]}
                for other in in_flight
                if other["number"] != p["number"]
            ]
        }
        for p in found
        if p["stage"] == "review"
    ]
