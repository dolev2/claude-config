"""rank_issues.py: the ranking dev-plan, dev-code and dev-next pick issues by."""

import importlib.util
import json
from pathlib import Path

import pytest

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
    subs=(),
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
        "subIssues": {"nodes": [dict(sub) for sub in subs]},
    }


def issues(*nodes):
    return [rank_issues.parse_issue(n) for n in nodes]


def numbers(ranked):
    return [i.number for i in ranked]


def by_number(ranked):
    return {i.number: i for i in ranked}


def test_indirect_waiters_count():
    # 1 -> 2 -> 3, and 4 -> 3: issue 1 has two waiting, issue 4 one.
    ranked = rank_issues.rank(
        issues(
            node(4, blocking=[3]), node(3), node(2, blocking=[3]), node(1, blocking=[2])
        )
    )
    # Fewest waiting first (S-1.42): the blocked 3 is listed first, and skipped.
    assert numbers(ranked) == [3, 2, 4, 1]
    assert ranked[-1].waiting == [2, 3]


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
    assert by_number(ranked)[1].waiting == [2, 3, 4]


def test_waiters_outside_the_given_issues_add_no_weight():
    # 9 is not in the sprint, so it is not in the list passed in.
    ranked = rank_issues.rank(issues(node(1, blocking=[9]), node(2, blocking=[1])))
    assert numbers(ranked) == [1, 2]
    assert ranked[0].waiting == []


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
    assert numbers(ranked) == [4, 2, 3, 1]


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
    assert numbers(ranked)[:2] == [5, 2]
    assert ranked[0].kind == "process"


def test_bug_comes_before_weight_like_process():
    ranked = rank_issues.rank(
        issues(node(1, blocking=[2]), node(2), node(3, labels=("bug",)))
    )
    assert numbers(ranked) == [3, 2, 1]
    assert ranked[0].kind == "bug"


def test_weight_orders_within_process():
    ranked = rank_issues.rank(
        issues(
            node(1, labels=("process",)),
            node(2, labels=("process",), blocking=[3]),
            node(3),
        )
    )
    assert numbers(ranked) == [1, 2, 3]


def test_status_tier_stays_above_process():
    """`process` orders only within its tier; a bug does not (the next tests)."""
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
    kept, on_hold, paused = rank_issues.split_on_hold(ranked)
    assert numbers(kept) == [2, 3]
    assert numbers(on_hold) == [4, 1]
    assert paused == []


def test_an_issue_waiting_on_a_held_one_stays_blocked():
    ranked = rank_issues.rank(
        issues(
            node(1, labels=("costs-money",), blocking=[2]),
            node(2, blocked_by=[(1, "OPEN")]),
            node(3),
        )
    )
    kept, _, _ = rank_issues.split_on_hold(ranked)
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


EXECUTE_AND_PLAN = ["needs-repair", "ready-to-execute", "explore"]


def test_a_bug_comes_before_a_new_task_of_a_later_tier():
    """#202: an approved task that two issues wait on no longer passes a bug."""
    ranked = rank_issues.rank(
        issues(
            node(1, status="ready-to-execute", blocking=[2, 3]),
            node(2, blocked_by=[(1, "OPEN")]),
            node(3, blocked_by=[(1, "OPEN")]),
            node(4, status="explore", labels=("bug",)),
        ),
        statuses=EXECUTE_AND_PLAN,
    )
    assert numbers(ranked)[:2] == [4, 1]


@pytest.mark.parametrize(
    ("nodes", "statuses", "first"),
    [
        pytest.param(
            [
                node(1, status="needs-repair"),
                node(2, status="ready-to-execute", labels=("bug",)),
            ],
            EXECUTE_AND_PLAN,
            [1, 2],
            id="a-repair-stays-before-a-bug",
        ),
        pytest.param(
            [node(1, status="needs-repair"), node(2, labels=("bug",))],
            None,
            [2, 1],
            id="no-repair-first-without-tiers",
        ),
        pytest.param(
            [
                node(1, status="explore", labels=("process",)),
                node(2, status="explore", labels=("bug",)),
            ],
            EXECUTE_AND_PLAN,
            [2, 1],
            id="a-bug-before-process-in-the-same-tier",
        ),
        pytest.param(
            [
                node(1, status="ready-to-execute", labels=("process",)),
                node(2, status="explore", labels=("bug",)),
            ],
            EXECUTE_AND_PLAN,
            [2, 1],
            id="a-bug-before-process-of-an-earlier-tier",
        ),
        pytest.param(
            [node(1, labels=("process",)), node(2, labels=("bug",))],
            None,
            [2, 1],
            id="a-bug-before-process-without-tiers",
        ),
    ],
)
def test_the_bug_first_rule(nodes, statuses, first):
    assert numbers(rank_issues.rank(issues(*nodes), statuses)) == first


def test_an_issue_with_both_labels_is_a_bug():
    [issue] = issues(node(1, labels=("process", "bug")))
    assert issue.kind == "bug"


def test_a_blocked_bug_stays_listed_and_the_free_task_is_the_first_unblocked():
    ranked = rank_issues.rank(
        issues(
            node(1, status="explore", labels=("bug",), blocked_by=[(2, "OPEN")]),
            node(2, status="ready-to-execute", blocking=[1]),
            node(3, status="ready-to-execute"),
        ),
        statuses=EXECUTE_AND_PLAN,
    )
    # 2 and 3 are both approved; 3 has fewer waiting, so it comes first (S-1.42).
    assert numbers(ranked) == [1, 3, 2]
    assert ranked[0].blocked
    assert next(i for i in ranked if not i.blocked).number == 3


def test_an_umbrella_with_an_open_sub_issue_is_marked(capsys):
    # The bug of #250: dev-code took the first unblocked row, umbrella or not.
    [umbrella] = issues(
        node(1, status="ready-to-execute", subs=[{"number": 2, "state": "OPEN"}])
    )
    assert umbrella.umbrella
    assert not umbrella.blocked
    rank_issues.print_ranking("W1", [umbrella], [], [])
    row = capsys.readouterr().out.splitlines()[1]
    assert row.endswith("issue 1  UMBRELLA, open sub-issues #2")


@pytest.mark.parametrize(
    "subs, expected",
    [
        ([], []),
        ([{"number": 2, "state": "CLOSED"}], []),
        (
            [
                {"number": 2, "state": "CLOSED"},
                {"number": 3, "state": "OPEN"},
                {"number": 4, "state": "OPEN", "repository": "o/other"},
            ],
            ["#3", "o/other#4"],
        ),
    ],
)
def test_only_open_sub_issues_make_an_umbrella(subs, expected):
    [issue] = issues(node(1, subs=subs))
    assert issue.open_subs == expected
    assert issue.umbrella == bool(expected)


def test_a_node_without_sub_issues_is_no_umbrella():
    bare = node(1)
    del bare["subIssues"]
    assert rank_issues.parse_issue(bare).open_subs == []


def test_the_json_output_carries_the_open_sub_issues(monkeypatch, capsys):
    nodes = [node(1, subs=[{"number": 2, "state": "OPEN"}]), node(2)]
    monkeypatch.setattr(rank_issues, "open_issue_nodes", lambda repo: nodes)
    rank_issues.main(["--repo", "o/r", "--json"])
    rows = json.loads(capsys.readouterr().out)["issues"]
    assert {row["number"]: row["open_subs"] for row in rows} == {1: ["#2"], 2: []}


# S-1.42 (#295): a topic is finished before the next.


def started(nodes, statuses=None):
    """rank() over the sprint nodes, with the started umbrellas read from `nodes`."""
    in_sprint = [n for n in nodes if n["milestone"]]
    parsed = rank_issues.with_started_umbrellas(issues(*in_sprint), nodes)
    return rank_issues.rank(parsed, statuses)


def umbrella(number, subs, milestone=(1, "W1"), status="explore"):
    return node(number, status=status, milestone=milestone, subs=subs)


def test_fewest_waiting_comes_first_within_a_group():
    ranked = rank_issues.rank(
        issues(node(1, blocking=[3, 4]), node(2, blocking=[3]), node(3), node(4))
    )
    assert numbers(ranked) == [3, 4, 2, 1]


def test_a_sub_issue_of_a_started_umbrella_beats_a_lone_bottleneck():
    """The check of the issue: the umbrella's task, not the one many wait on."""
    ranked = started(
        [
            node(1, blocking=[3, 4, 5]),
            node(2),
            node(3, blocked_by=[(1, "OPEN")]),
            node(4, blocked_by=[(1, "OPEN")]),
            node(5, blocked_by=[(1, "OPEN")]),
            umbrella(
                10, [{"number": 9, "state": "CLOSED"}, {"number": 2, "state": "OPEN"}]
            ),
        ]
    )
    free = [i for i in ranked if not i.blocked and not i.umbrella]
    assert free[0].number == 2
    assert free[0].umbrella_of == 10
    assert free[0].reason == "umbrella"


@pytest.mark.parametrize(
    "labels, reason", [(("bug",), "bug"), (("task", "process"), "process")]
)
def test_bug_and_process_stay_before_a_started_umbrella(labels, reason):
    ranked = started(
        [
            node(1),
            node(2, labels=labels),
            umbrella(
                10, [{"number": 9, "state": "CLOSED"}, {"number": 1, "state": "OPEN"}]
            ),
        ]
    )
    assert numbers(ranked)[:2] == [2, 1]
    assert ranked[0].reason == reason


@pytest.mark.parametrize(
    "sub_status, is_started",
    [
        pytest.param("explore", False, id="all-open-in-explore"),
        pytest.param("ready-to-execute", False, id="an-approved-plan-is-no-start"),
        pytest.param("in-review", True, id="a-sub-in-review"),
        pytest.param("needs-repair", True, id="a-sub-in-repair"),
    ],
)
def test_when_an_umbrella_has_started(sub_status, is_started):
    nodes = [
        node(1),
        node(2, status=sub_status),
        umbrella(10, [{"number": 1, "state": "OPEN"}, {"number": 2, "state": "OPEN"}]),
    ]
    assert (rank_issues.started_umbrellas(nodes).get(1) == 10) is is_started


def test_a_closed_sub_issue_starts_the_umbrella():
    nodes = [
        umbrella(10, [{"number": 1, "state": "OPEN"}, {"number": 2, "state": "CLOSED"}])
    ]
    assert rank_issues.started_umbrellas(nodes) == {1: 10}


def test_a_sub_issue_of_another_repo_does_not_start_it():
    subs = [
        {"number": 1, "state": "OPEN"},
        {"number": 2, "state": "CLOSED", "repository": "o/other"},
    ]
    assert rank_issues.started_umbrellas([umbrella(10, subs)]) == {}


def test_an_umbrella_outside_the_sprint_counts():
    ranked = started(
        [
            node(1, blocking=[2]),
            node(2, blocked_by=[(1, "OPEN")]),
            node(3),
            umbrella(
                10,
                [{"number": 9, "state": "CLOSED"}, {"number": 1, "state": "OPEN"}],
                milestone=(2, "W2"),
            ),
        ]
    )
    assert ranked[0].number == 1
    assert ranked[0].umbrella_of == 10


def test_the_status_tier_still_comes_before_process_and_umbrella():
    ranked = started(
        [
            node(1, status="explore", labels=("process",)),
            node(2, status="explore"),
            node(3, status="ready-to-execute"),
            umbrella(
                10, [{"number": 9, "state": "CLOSED"}, {"number": 2, "state": "OPEN"}]
            ),
        ],
        statuses=EXECUTE_AND_PLAN,
    )
    assert numbers(ranked)[:3] == [3, 1, 2]


def test_the_lone_reason_is_fewest_waiting():
    [issue] = rank_issues.rank(issues(node(1)))
    assert issue.reason == "fewest-waiting"


def test_a_paused_issue_leaves_the_ranking_but_still_adds_weight():
    ranked = rank_issues.rank(
        issues(
            node(1, labels=("task", "paused"), blocking=[2]),
            node(2, blocked_by=[(1, "OPEN")]),
            node(3),
        )
    )
    kept, on_hold, paused = rank_issues.split_on_hold(ranked)
    assert numbers(kept) == [2, 3]
    assert kept[0].blocked
    assert on_hold == []
    assert numbers(paused) == [1]
    assert paused[0].waiting == [2]


@pytest.mark.parametrize(
    "labels", [("task", "paused"), ("task", "paused", "costs-money")]
)
def test_include_costs_money_does_not_bring_back_a_paused_issue(labels):
    ranked = rank_issues.rank(issues(node(1, labels=labels), node(2)))
    kept, on_hold, paused = rank_issues.split_on_hold(ranked, include_costs_money=True)
    assert numbers(kept) == [2]
    assert on_hold == []
    assert numbers(paused) == [1]


def run_main(monkeypatch, capsys, nodes, *flags):
    monkeypatch.setattr(rank_issues, "open_issue_nodes", lambda repo: nodes)
    rank_issues.main(["--repo", "o/r", *flags])
    return capsys.readouterr().out


PAUSE_NODES = [
    node(1, labels=("task", "paused"), blocking=[2]),
    node(2, blocked_by=[(1, "OPEN")]),
    node(3),
    umbrella(10, [{"number": 9, "state": "CLOSED"}, {"number": 3, "state": "OPEN"}]),
]


def test_the_text_output_names_paused_issues_and_the_reason(monkeypatch, capsys):
    lines = run_main(monkeypatch, capsys, PAUSE_NODES).splitlines()
    assert lines[-1] == "Paused by Dolev: #1 issue 1"
    row_2 = next(line for line in lines if line.startswith("#2 "))
    assert row_2.endswith("BLOCKED by #1 (paused)")
    row_3 = next(line for line in lines if line.startswith("#3 "))
    assert row_3.endswith("issue 3  FROM STARTED UMBRELLA #10")


def test_the_json_output_carries_paused_and_the_reason(monkeypatch, capsys):
    payload = json.loads(run_main(monkeypatch, capsys, PAUSE_NODES, "--json"))
    rows = {row["number"]: row for row in payload["issues"]}
    assert payload["paused"] == [1]
    assert payload["on_hold"] == []
    assert 1 not in rows
    assert rows[2]["paused_blockers"] == [1]
    assert (rows[3]["reason"], rows[3]["umbrella_of"]) == ("umbrella", 10)
    assert (rows[10]["reason"], rows[10]["umbrella_of"]) == ("fewest-waiting", None)
