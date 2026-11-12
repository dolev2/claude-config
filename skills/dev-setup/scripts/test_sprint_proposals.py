"""sprint_proposals.py: which backlog issues are approved proposals, and their stage."""

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sprint_proposals  # noqa: E402

GATE_BODY = (
    "### מה רוצים\n\ngoal\n\n### הקשר / קישורים\n\nאפיון: docs/specs/r.md S-1.2\n\n"
    "---\n### Plan\n\n_טרם נכתבה תוכנית._\n"
)


def node(number=1, status="backlog", labels=(), milestone="W1", subs=(), body=""):
    names = [f"status:{status}", *labels] if status else list(labels)
    return {
        "number": number,
        "title": f"issue {number}",
        "body": body,
        "labels": {"nodes": [{"name": name} for name in names]},
        "milestone": {"number": 1, "title": milestone, "state": "OPEN"}
        if milestone
        else None,
        "blockedBy": {"nodes": []},
        "blocking": {"nodes": []},
        "subIssues": {"nodes": [{"number": n, "state": "OPEN"} for n in subs]},
    }


def pr(number=40, state="open", branch="claude/spec-x", questions="_אין._"):
    return {
        "number": number,
        "state": state,
        "branch": branch,
        "body": f"Refs #1\n\n### שאלות פתוחות\n{questions}\n",
        "headSha": f"sha{number}",
    }


@pytest.mark.parametrize(
    ("issue", "expected"),
    [
        (node(), True),
        (node(body=GATE_BODY), True),
        (node(milestone=None), False),
        (node(milestone="W2"), False),
        (node(labels=("bug",)), False),
        (node(subs=[5]), False),
        (node(labels=("costs-money",)), False),
        (node(labels=("paused",)), False),
        (node(status="explore"), False),
        (node(status=None), False),
    ],
    ids=[
        "backlog-in-sprint",
        "sent-back-by-the-gate",
        "no-milestone",
        "other-sprint",
        "bug",
        "umbrella",
        "costs-money",
        "paused",
        "not-backlog",
        "no-status",
    ],
)
def test_is_proposal(issue, expected):
    assert sprint_proposals.is_proposal(issue, "W1") is expected


@pytest.mark.parametrize(
    ("prs", "claimed", "expected"),
    [
        ([], False, ("waiting", None)),
        ([], True, ("writing", None)),
        ([pr()], True, ("writing", 40)),
        ([pr(questions="- [ ] which?\n- [x] done")], False, ("questions", 40)),
        ([pr(questions="- [x] done")], False, ("review", 40)),
        ([pr(state="merged")], False, ("breakdown", 40)),
        ([pr(state="closed")], False, ("waiting", None)),
        ([pr(branch="claude/issue-1-code")], False, ("waiting", None)),
        ([pr(41, "merged"), pr(42)], False, ("review", 42)),
    ],
    ids=[
        "waiting",
        "writing",
        "writing-a-revision",
        "questions",
        "review",
        "breakdown",
        "closed-unmerged",
        "not-a-spec-branch",
        "open-wins-over-merged",
    ],
)
def test_stage(prs, claimed, expected):
    name, found = sprint_proposals.stage(prs, claimed)
    assert (name, found["number"] if found else None) == expected


@pytest.mark.parametrize(
    ("prs", "claimed", "expected"),
    [
        ([], False, ("replan", None)),
        ([pr(state="merged")], False, ("replan", None)),
        ([pr()], False, ("review", 40)),
        ([], True, ("writing", None)),
    ],
    ids=["no-pr", "merged-pr-is-no-breakdown", "open-pr-wins", "claimed-wins"],
)
def test_stage_of_an_issue_an_open_part_names(prs, claimed, expected):
    name, found = sprint_proposals.stage(prs, claimed, ["S-2.3"])
    assert (name, found["number"] if found else None) == expected


def test_a_box_outside_the_questions_section_is_no_question():
    body = "### מה נוסף\n- [ ] a part\n\n### שאלות פתוחות\n_אין._\n"
    assert not sprint_proposals.has_open_question(body)


def test_proposals_are_by_number_with_their_stage():
    nodes = [node(7), node(3), node(5, status="explore"), node(9, milestone="W2")]
    found = sprint_proposals.proposals(
        nodes, "W1", [7], lambda n: [pr(40)] if n == 3 else []
    )
    assert [(p["number"], p["stage"], p["pr"]) for p in found] == [
        (3, "review", 40),
        (7, "writing", None),
    ]


def test_proposals_carry_the_open_parts_that_name_them():
    found = sprint_proposals.proposals(
        [node(3), node(6)], "W1", [], lambda n: [], {6: ["S-2.3"]}
    )
    assert [(p["number"], p["stage"], p["parts"]) for p in found] == [
        (3, "waiting", []),
        (6, "replan", ["S-2.3"]),
    ]


def test_spec_split_sends_one_spec_child():
    found = [
        {"number": 3, "title": "a", "stage": "waiting"},
        {"number": 4, "title": "b", "stage": "waiting"},
    ]
    dispatch, held = sprint_proposals.spec_split(found, "docs/specs/r.md")
    assert [row["number"] for row in dispatch] == [3]
    assert held == [{"number": 4, "with": [3], "files": ["docs/specs/r.md"]}]


@pytest.mark.parametrize("in_flight", ["writing", "questions", "review"])
def test_an_open_spec_holds_the_next_proposal(in_flight):
    found = [
        {"number": 3, "title": "a", "stage": in_flight},
        {"number": 4, "title": "b", "stage": "waiting"},
    ]
    dispatch, held = sprint_proposals.spec_split(found, "f")
    assert dispatch == []
    assert held == [{"number": 4, "with": [3], "files": ["f"]}]


def test_spec_split_with_nothing_waiting_is_empty():
    found = [{"number": 3, "title": "a", "stage": "breakdown"}]
    assert sprint_proposals.spec_split(found, "f") == ([], [])
