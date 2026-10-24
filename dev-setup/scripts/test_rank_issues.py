"""rank_issues.py: the ranking dev-plan, dev-code and dev-next pick issues by."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "rank_issues.py"
spec = importlib.util.spec_from_file_location("rank_issues", SCRIPT)
rank_issues = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rank_issues)


def node(number, status="explore", owner="claude", milestone=(1, "W1"), blocked_by=(), blocking=()):
    return {
        "number": number,
        "title": f"issue {number}",
        "labels": {"nodes": [{"name": f"status:{status}"}, {"name": f"owner:{owner}"}, {"name": "task"}]},
        "milestone": {"number": milestone[0], "title": milestone[1], "state": "OPEN"} if milestone else None,
        "blockedBy": {"nodes": [{"number": n, "state": s} for n, s in blocked_by]},
        "blocking": {"nodes": [{"number": n, "state": "OPEN"} for n in blocking]},
    }


def issues(*nodes):
    return [rank_issues.parse_issue(n) for n in nodes]


def numbers(ranked):
    return [i.number for i in ranked]


def test_indirect_waiters_count():
    # 1 -> 2 -> 3, and 4 -> 3: issue 1 has two waiting, issue 4 one.
    ranked = rank_issues.rank(issues(node(4, blocking=[3]), node(3), node(2, blocking=[3]), node(1, blocking=[2])))
    assert numbers(ranked) == [1, 2, 4, 3]
    assert ranked[0].waiting == [2, 3]


def test_a_shared_waiter_counts_once():
    # 1 -> 2 -> 4 and 1 -> 3 -> 4: three waiting, not four.
    ranked = rank_issues.rank(issues(node(1, blocking=[2, 3]), node(2, blocking=[4]), node(3, blocking=[4]), node(4)))
    assert ranked[0].waiting == [2, 3, 4]


def test_waiters_outside_the_given_issues_add_no_weight():
    # 9 is not in the sprint, so it is not in the list passed in.
    ranked = rank_issues.rank(issues(node(1, blocking=[9]), node(2, blocking=[1])))
    assert numbers(ranked) == [2, 1]
    assert ranked[1].waiting == []


def test_a_dependency_cycle_terminates():
    ranked = rank_issues.rank(issues(node(1, blocking=[2]), node(2, blocking=[1])))
    assert [i.waiting for i in ranked] == [[2], [1]]


def test_status_order_is_the_tier_before_weight():
    ranked = rank_issues.rank(
        issues(node(1, status="explore", blocking=[2, 3]), node(2), node(3), node(4, status="plan-questions")),
        statuses=["plan-questions", "explore"],
    )
    assert numbers(ranked) == [4, 1, 2, 3]


def test_owner_and_status_filter_but_others_still_add_weight():
    # 2 is Dolev's backlog: not a candidate, but it still waits on 1.
    ranked = rank_issues.rank(
        issues(node(1, blocking=[2]), node(2, status="backlog", owner="dolev"), node(3, status="in-review")),
        statuses=["explore"],
        owner="claude",
    )
    assert numbers(ranked) == [1]
    assert ranked[0].waiting == [2]


def test_only_open_blockers_block():
    (issue,) = issues(node(1, blocked_by=[(5, "CLOSED"), (6, "OPEN")]))
    assert issue.open_blockers == [6]
    assert issue.blocked


def test_current_sprint_is_the_lowest_open_milestone_with_open_issues():
    nodes = [node(1, milestone=(3, "W2")), node(2, milestone=(2, "W1")), node(3, milestone=None)]
    assert rank_issues.current_sprint(nodes) == "W1"


def test_closed_milestones_are_not_the_sprint():
    closed = node(1, milestone=(1, "W0"))
    closed["milestone"]["state"] = "CLOSED"
    assert rank_issues.current_sprint([closed, node(2, milestone=(2, "W1"))]) == "W1"
