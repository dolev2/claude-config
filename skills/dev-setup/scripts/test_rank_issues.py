"""rank_issues.py: the ranking dev-plan, dev-code and dev-next pick issues by."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "rank_issues.py"
spec = importlib.util.spec_from_file_location("rank_issues", SCRIPT)
rank_issues = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rank_issues)


def node(
    number,
    status="explore",
    milestone=(1, "W1"),
    blocked_by=(),
    blocking=(),
    labels=("task",),
):
    names = [f"status:{status}", *labels]
    return {
        "number": number,
        "title": f"issue {number}",
        "labels": {"nodes": [{"name": name} for name in names]},
        "milestone": {"number": milestone[0], "title": milestone[1], "state": "OPEN"}
        if milestone
        else None,
        "blockedBy": {"nodes": [{"number": n, "state": s} for n, s in blocked_by]},
        "blocking": {"nodes": [{"number": n, "state": "OPEN"} for n in blocking]},
    }


def issues(*nodes):
    return [rank_issues.parse_issue(n) for n in nodes]


def numbers(ranked):
    return [i.number for i in ranked]


def test_indirect_waiters_count():
    # 1 -> 2 -> 3, and 4 -> 3: issue 1 has two waiting, issue 4 one.
    ranked = rank_issues.rank(
        issues(
            node(4, blocking=[3]), node(3), node(2, blocking=[3]), node(1, blocking=[2])
        )
    )
    assert numbers(ranked) == [1, 2, 4, 3]
    assert ranked[0].waiting == [2, 3]


def test_a_shared_waiter_counts_once():
    # 1 -> 2 -> 4 and 1 -> 3 -> 4: three waiting, not four.
    ranked = rank_issues.rank(
        issues(
            node(1, blocking=[2, 3]),
            node(2, blocking=[4]),
            node(3, blocking=[4]),
            node(4),
        )
    )
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
        issues(
            node(1, status="explore", blocking=[2, 3]),
            node(2),
            node(3),
            node(4, status="plan-questions"),
        ),
        statuses=["plan-questions", "explore"],
    )
    assert numbers(ranked) == [4, 1, 2, 3]


def test_status_filters_but_others_still_add_weight():
    # 2 is Dolev's backlog: not a candidate, but it still waits on 1.
    ranked = rank_issues.rank(
        issues(
            node(1, blocking=[2]),
            node(2, status="backlog"),
            node(3, status="in-review"),
        ),
        statuses=["explore"],
    )
    assert numbers(ranked) == [1]
    assert ranked[0].waiting == [2]


def test_process_comes_before_weight():
    ranked = rank_issues.rank(
        issues(
            node(1, blocking=[2, 3, 4]),
            node(2),
            node(3),
            node(4),
            node(5, labels=("task", "process")),
        )
    )
    assert numbers(ranked)[:2] == [5, 1]
    assert ranked[0].kind == "process"


def test_bug_comes_before_weight_like_process():
    ranked = rank_issues.rank(
        issues(node(1, blocking=[2]), node(2), node(3, labels=("bug",)))
    )
    assert numbers(ranked) == [3, 1, 2]
    assert ranked[0].kind == "bug"


def test_weight_orders_within_process():
    ranked = rank_issues.rank(
        issues(
            node(1, labels=("process",)),
            node(2, labels=("process",), blocking=[3]),
            node(3),
        )
    )
    assert numbers(ranked) == [2, 1, 3]


def test_status_tier_stays_above_process():
    ranked = rank_issues.rank(
        issues(
            node(1, status="explore", labels=("process",)),
            node(2, status="plan-questions"),
        ),
        statuses=["plan-questions", "explore"],
    )
    assert numbers(ranked) == [2, 1]


def test_a_blocked_process_issue_stays_listed_and_flagged():
    ranked = rank_issues.rank(
        issues(
            node(1, labels=("process",), blocked_by=[(2, "OPEN")]),
            node(2, blocking=[1]),
        )
    )
    assert numbers(ranked) == [1, 2]
    assert ranked[0].blocked


def test_costs_money_issues_go_on_hold():
    ranked = rank_issues.rank(
        issues(
            node(1, labels=("task", "costs-money"), blocking=[2, 3]),
            node(2),
            node(3),
            node(4, labels=("process", "costs-money")),
        )
    )
    kept, on_hold = rank_issues.split_on_hold(ranked)
    assert numbers(kept) == [2, 3]
    assert numbers(on_hold) == [4, 1]


def test_an_issue_waiting_on_a_held_one_stays_blocked():
    ranked = rank_issues.rank(
        issues(
            node(1, labels=("costs-money",), blocking=[2]),
            node(2, blocked_by=[(1, "OPEN")]),
            node(3),
        )
    )
    kept, _ = rank_issues.split_on_hold(ranked)
    assert numbers(kept) == [2, 3]
    assert kept[0].blocked


def test_only_open_blockers_block():
    (issue,) = issues(node(1, blocked_by=[(5, "CLOSED"), (6, "OPEN")]))
    assert issue.open_blockers == [6]
    assert issue.blocked


def test_current_sprint_is_the_lowest_open_milestone_with_open_issues():
    nodes = [
        node(1, milestone=(3, "W2")),
        node(2, milestone=(2, "W1")),
        node(3, milestone=None),
    ]
    assert rank_issues.current_sprint(nodes) == "W1"


def test_closed_milestones_are_not_the_sprint():
    closed = node(1, milestone=(1, "W0"))
    closed["milestone"]["state"] = "CLOSED"
    assert rank_issues.current_sprint([closed, node(2, milestone=(2, "W1"))]) == "W1"


def test_active_issues_without_a_sprint_are_listed_apart():
    nodes = [
        node(42, status="plan-questions", milestone=None),
        node(7, status="explore", milestone=None),
        node(8, status="backlog", milestone=None),  # on purpose
        node(9, status="done", milestone=None),
        node(3, status="explore"),  # in a sprint
    ]
    assert numbers(rank_issues.active_without_sprint(nodes)) == [7, 42]


def test_the_text_output_names_them_last(capsys):
    no_sprint = issues(node(42, status="plan-questions", milestone=None))
    rank_issues.print_ranking("W1", [], [], no_sprint)
    last = capsys.readouterr().out.splitlines()[-1]
    assert last == "Active, no sprint: #42 issue 42 (plan-questions)"


# Links to another repo's issues (claude-config #164).


def test_a_blocker_of_another_repo_blocks_but_adds_no_weight():
    # dolev2/other#2 blocks #1. Read by its number alone, it gave weight to #2.
    one = node(1)
    one["blockedBy"]["nodes"].append(
        {"number": 2, "state": "OPEN", "repository": "dolev2/other"}
    )
    two = node(2)
    two["blocking"]["nodes"].append(
        {"number": 1, "state": "OPEN", "repository": "dolev2/other"}
    )
    first, second = rank_issues.rank(issues(one, two))
    assert [first.waiting, second.waiting] == [[], []]
    assert first.open_blockers == [] and first.outside_blockers == ["dolev2/other#2"]
    assert first.blocked
    assert not second.blocked
