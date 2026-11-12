"""sprint_state.py: the sprint as one JSON object, for the sprint orchestrator."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("sprint_state", HERE / "sprint_state.py")
sprint_state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sprint_state)
import issue_body  # noqa: E402
import pipeline_shas  # noqa: E402
import sprint_github  # noqa: E402


def body(files=(), branch=None, questions="_אין שאלות פתוחות._"):
    bullets = "\n".join(f"- `{f}`: changes" for f in files)
    branch_line = f"**Branch:** `{branch}`\n\n" if branch else ""
    return (
        "### מה רוצים\n\ngoal\n\n### הקשר / קישורים\n\ncontext\n\n---\n"
        f"### Plan\n\n{branch_line}##### קבצים שצפויים להשתנות\n{bullets}\n\n"
        f"### שאלות פתוחות\n\n{questions}\n"
    )


def node(
    number,
    status="ready-to-execute",
    files=(),
    blocked_by=(),
    blocking=(),
    labels=("task",),
    subs=(),
    closed_subs=(),
    prs=(),
    milestone="W1",
    branch=None,
    questions="_אין שאלות פתוחות._",
):
    names = [f"status:{status}", *labels]
    return {
        "number": number,
        "title": f"issue {number}",
        "body": body(files, branch, questions),
        "labels": {"nodes": [{"name": name} for name in names]},
        "milestone": {"number": 1, "title": milestone, "state": "OPEN"},
        "blockedBy": {"nodes": [{"number": n, "state": s} for n, s in blocked_by]},
        "blocking": {"nodes": [{"number": n, "state": "OPEN"} for n in blocking]},
        "closedByPullRequestsReferences": {"totalCount": len(prs)},
        "closingPullRequests": [{"number": p, "headSha": f"sha{p}"} for p in prs],
        "parent": None,
        "subIssues": {
            "nodes": [{"number": n, "state": "OPEN"} for n in subs]
            + [{"number": n, "state": "CLOSED"} for n in closed_subs]
        },
    }


SPEC = "docs/specs/r.md"


def no_pr_status(pr):
    raise AssertionError(f"PR {pr['number']} should not be read")


def run(
    *nodes,
    claimed=(),
    status_of=no_pr_status,
    branches=None,
    pr_files=None,
    spec_prs=None,
):
    branches = branches or {}
    pr_files = pr_files or {}
    spec_prs = spec_prs or {}
    return sprint_state.state(
        list(nodes),
        "W1",
        list(claimed),
        status_of,
        lambda branch: set(branches.get(branch, ())),
        lambda number: set(pr_files.get(number, ())),
        lambda number: spec_prs.get(number, []),
        SPEC,
    )


def clean(pr):
    return {"mergeable_state": "clean", "ci": "success"}


def numbers(rows):
    return [row["number"] for row in rows]


@pytest.mark.parametrize(
    ("status", "prompt"),
    [
        ("explore", "תחקור את #1"),
        ("ready-to-execute", "תקודד את #1"),
        ("needs-repair", "תקודד את #1"),
    ],
)
def test_claude_turn_is_dispatched_with_its_prompt(status, prompt):
    [row] = run(node(1, status))["dispatch"]
    assert row["prompt"] == prompt
    assert row["status"] == status


def test_repairs_go_first_then_approved_plans_then_plans_to_write():
    result = run(
        node(1, "explore"), node(2, "ready-to-execute"), node(3, "needs-repair")
    )
    assert numbers(result["dispatch"]) == [3, 2, 1]


@pytest.mark.parametrize(
    "bug_status", ["ready-to-execute", "explore"], ids=["same-tier", "later-tier"]
)
def test_a_bug_goes_out_before_a_new_task_that_others_wait_on(bug_status):
    """#202: the bug-first rule reaches the orchestrator through the ranking."""
    result = run(
        node(1, "ready-to-execute", blocking=[2, 3]),
        node(2, "explore", blocked_by=[(1, "OPEN")]),
        node(3, "explore", blocked_by=[(1, "OPEN")]),
        node(4, bug_status, labels=("bug",)),
    )
    assert numbers(result["dispatch"]) == [4, 1]


def test_dolev_turn_keeps_the_tier_first_even_for_a_bug():
    """#202 picks for Claude only: his questions come before PRs to review."""
    result = run(node(1, "plan-questions"), node(2, "in-review", labels=("bug",)))
    assert numbers(result["waiting_dolev"]) == [1, 2]


@pytest.mark.parametrize(
    "issue",
    [
        node(1, blocked_by=[(9, "OPEN")]),
        node(1, labels=("task", "costs-money")),
        node(1, subs=[5]),
        node(1, "backlog", labels=("bug",)),
        node(1, "done"),
        node(1, "waiting-approval"),
    ],
    ids=["blocked", "costs-money", "umbrella", "backlog-bug", "done", "dolev-turn"],
)
def test_what_is_never_dispatched(issue):
    assert run(issue)["dispatch"] == []


def test_an_umbrella_whose_subs_are_all_closed_is_dispatched():
    result = run(node(1, closed_subs=[5, 6]))
    assert numbers(result["dispatch"]) == [1]
    assert result["umbrellas"] == []


def test_an_umbrella_with_an_open_sub_is_listed_apart():
    result = run(node(1, subs=[6], closed_subs=[5]), node(2, "done", subs=[7]))
    assert result["dispatch"] == []
    assert result["umbrellas"] == [{"number": 1, "open_subs": ["#6"]}]


def test_an_umbrella_held_for_another_reason_is_not_listed_as_one():
    result = run(
        node(1, subs=[6], blocked_by=[(9, "OPEN")]), node(2, subs=[7]), claimed=[2]
    )
    assert result["umbrellas"] == []
    assert numbers(result["blocked"]) == [1]


def test_an_open_sub_in_another_repo_is_named_with_its_repo():
    umbrella = node(1)
    umbrella["subIssues"]["nodes"] = [
        {"number": 3, "state": "OPEN", "repository": "acme/other"}
    ]
    assert run(umbrella)["umbrellas"] == [{"number": 1, "open_subs": ["acme/other#3"]}]


def test_a_closed_blocker_does_not_block():
    assert numbers(run(node(1, blocked_by=[(9, "CLOSED")]))["dispatch"]) == [1]


def test_blocked_and_on_hold_are_listed_apart():
    result = run(
        node(1, blocked_by=[(9, "OPEN")]), node(2, labels=("task", "costs-money"))
    )
    assert result["blocked"] == [
        {"number": 1, "blocked_by": [9], "outside_blockers": [], "paused_blockers": []}
    ]
    assert result["on_hold"] == [2]


def test_a_claimed_issue_is_not_dispatched_again():
    assert run(node(1), node(2), claimed=[1])["dispatch"][0]["number"] == 2


def test_a_file_shared_with_a_claimed_issue_holds_the_issue():
    result = run(node(1, files=["a.py"]), node(2, files=["a.py", "b.py"]), claimed=[1])
    assert result["dispatch"] == []
    assert result["held_by_overlap"] == [{"number": 2, "with": [1], "files": ["a.py"]}]


def test_a_file_shared_with_an_issue_in_review_holds_the_issue():
    result = run(
        node(1, "in-review", files=["a.py"], prs=[40]),
        node(2, files=["a.py"]),
        status_of=lambda pr: {"mergeable_state": "clean", "ci": "success"},
    )
    assert numbers(result["held_by_overlap"]) == [2]


def test_two_ready_issues_sharing_a_file_never_go_out_together():
    result = run(node(1, files=["a.py"]), node(2, files=["a.py"]))
    assert numbers(result["dispatch"]) == [1]
    assert result["held_by_overlap"] == [{"number": 2, "with": [1], "files": ["a.py"]}]


def test_an_issue_after_a_held_one_is_still_dispatched():
    result = run(
        node(1, files=["a.py"]), node(2, files=["a.py"]), node(3, files=["c.py"])
    )
    assert numbers(result["dispatch"]) == [1, 3]
    assert numbers(result["held_by_overlap"]) == [2]


def test_readme_and_claude_md_are_not_an_overlap():
    shared = ["README.md", ".claude/CLAUDE.md"]
    result = run(node(1, files=shared), node(2, files=shared))
    assert numbers(result["dispatch"]) == [1, 2]


def test_waiting_dolev_lists_his_turn():
    result = run(node(1, "plan-questions"), node(2, "waiting-approval"))
    assert result["waiting_dolev"] == [
        {"number": 1, "title": "issue 1", "status": "plan-questions"},
        {"number": 2, "title": "issue 2", "status": "waiting-approval"},
    ]


def test_merge_queue_carries_the_pr_head_and_its_checks():
    seen = []

    def status_of(pr):
        seen.append(pr)
        return {"mergeable_state": "behind", "ci": "pending"}

    result = run(
        node(1, "in-review", prs=[40]), node(2, "in-review"), status_of=status_of
    )
    assert result["merge_queue"] == [
        {
            "number": 1,
            "pr": 40,
            "head_sha": "sha40",
            "mergeable_state": "behind",
            "ci": "pending",
            "overlaps": [],
        }
    ]
    assert seen == [{"number": 40, "headSha": "sha40"}]


def test_a_manual_task_waits_for_dolev_and_is_never_dispatched():
    # #75 (a Netlify check only Dolev can run) reached dispatch as ready-to-execute;
    # such a task now waits in plan-questions with its questions as checkboxes.
    manual = node(75, "plan-questions", questions="- [ ] מה מצאת ב-Netlify?")
    result = run(manual, node(2))
    assert numbers(result["dispatch"]) == [2]
    assert numbers(result["waiting_dolev"]) == [75]


def test_a_file_a_child_changed_off_plan_holds_the_issue_that_plans_it():
    # #196 after #164: the child changed audit_sprint.py without planning it.
    result = run(
        node(164, branch="claude/issue-164-x", files=["a.py"]),
        node(196, files=["audit_sprint.py"]),
        claimed=[164],
        branches={"claude/issue-164-x": ["a.py", "audit_sprint.py"]},
    )
    assert result["dispatch"] == []
    assert result["held_by_overlap"] == [
        {"number": 196, "with": [164], "files": ["audit_sprint.py"]}
    ]


def test_a_branch_not_pushed_yet_counts_only_the_planned_files():
    result = run(
        node(1, branch="claude/issue-1-x", files=["a.py"]),
        node(2, files=["b.py"]),
        claimed=[1],
    )
    assert numbers(result["dispatch"]) == [2]


def test_the_merge_queue_names_active_children_that_share_a_file():
    result = run(
        node(1, "in-review", prs=[40], files=["a.py"]),
        node(2, "explore", branch="claude/issue-2-x"),
        node(3, "ready-to-execute", files=["c.py"]),
        claimed=[2, 3],
        status_of=clean,
        branches={"claude/issue-2-x": ["audit_sprint.py", "README.md"]},
        pr_files={40: ["a.py", "audit_sprint.py", "README.md"]},
    )
    [queued] = result["merge_queue"]
    assert queued["overlaps"] == [{"number": 2, "files": ["audit_sprint.py"]}]


def test_a_pr_that_shares_nothing_has_no_overlaps():
    result = run(
        node(1, "in-review", prs=[40]),
        node(2, "in-review", prs=[41], files=["b.py"]),
        status_of=clean,
        pr_files={40: ["a.py"], 41: ["b.py"]},
    )
    assert [q["overlaps"] for q in result["merge_queue"]] == [[], []]


def test_another_pr_in_review_is_an_overlap_too():
    result = run(
        node(1, "in-review", prs=[40]),
        node(2, "in-review", prs=[41], files=["a.py"]),
        status_of=clean,
        pr_files={40: ["a.py"]},
    )
    assert result["merge_queue"][0]["overlaps"] == [{"number": 2, "files": ["a.py"]}]


@pytest.mark.parametrize(
    ("plan", "branch"),
    [
        ("**Branch:** `claude/issue-7-x`\n\n#### בקצרה", "claude/issue-7-x"),
        ("#### בקצרה\n- **הבעיה:** x", None),
        ("", None),
    ],
)
def test_plan_branch(plan, branch):
    assert issue_body.plan_branch(plan) == branch


def test_findings_are_data():
    result = run(node(1, "explore", files=["a.py"]), node(2, "explore", files=["a.py"]))
    [finding] = result["findings"]
    assert finding["code"] == "OVERLAP"
    assert finding["numbers"] == [1, 2]


def test_other_sprints_are_left_out():
    assert run(node(1, milestone="W2"))["dispatch"] == []


def test_an_empty_sprint_is_empty_everywhere():
    result = run()
    for key in ("dispatch", "held_by_overlap", "blocked", "waiting_dolev"):
        assert result[key] == []
    assert result["merge_queue"] == [] and result["findings"] == []


@pytest.mark.parametrize(
    ("runs", "summary"),
    [
        ([], "none"),
        ([{"status": "in_progress", "conclusion": None}], "pending"),
        (
            [
                {"status": "completed", "conclusion": "success"},
                {"status": "completed", "conclusion": "failure"},
            ],
            "failure",
        ),
        (
            [
                {"status": "completed", "conclusion": "success"},
                {"status": "completed", "conclusion": "skipped"},
            ],
            "success",
        ),
    ],
)
def test_ci_summary(runs, summary):
    assert sprint_github.ci_summary(runs) == summary


def fake_github(monkeypatch, nodes):
    monkeypatch.setattr(sprint_state, "current_repo", lambda: "acme/widgets")
    monkeypatch.setattr(sprint_state, "open_issue_nodes", lambda repo, with_body: nodes)
    monkeypatch.setattr(sprint_state, "api", lambda path: {"default_branch": "main"})


def test_a_failing_git_leaves_null_shas_and_the_rest_of_the_state(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(pipeline_shas, "PIPELINE_URL", str(tmp_path / "missing"))
    monkeypatch.setattr(sprint_state, "CACHE", tmp_path / "cache.git")
    fake_github(monkeypatch, [node(1), node(2)])
    sprint_state.main(["--claimed", "1"])
    out = capsys.readouterr()
    result = json.loads(out.out)
    assert numbers(result["dispatch"]) == [2]
    assert result["pipeline_sha"] is None and result["session_sha"] is None
    assert "pipeline-change check did not run" in out.err


def test_main_without_an_open_milestone_exits(monkeypatch):
    fake_github(monkeypatch, [])
    with pytest.raises(SystemExit, match="No open milestone"):
        sprint_state.main([])


def test_claimed_that_is_not_numbers_is_a_usage_error(monkeypatch):
    fake_github(monkeypatch, [node(1)])
    with pytest.raises(SystemExit) as exit_info:
        sprint_state.main(["--claimed", "abc"])
    assert exit_info.value.code == 2


SPEC_PATH = "docs/specs/pipeline.md"
SPEC_FILES = {SPEC_PATH: "# Pipeline\n\n## S-1.1 · Read\nText.\n"}
OPEN_PART = {
    "path": SPEC_PATH,
    "line": 3,
    "message": "S-1.1 is open, and no open issue points at it",
}


def spec_node(number, line=None, labels=("task",), milestone="W1"):
    """An open issue whose context section holds `line`, or no spec line at all."""
    found = node(number, labels=labels, milestone=milestone)
    if line:
        found["body"] = found["body"].replace("context", f"context\n\nאפיון: {line}")
    return found


def test_spec_gaps_of_all_open_issues():
    nodes = [
        spec_node(1, f"{SPEC_PATH} S-1.1"),
        spec_node(2),
        spec_node(3, f"{SPEC_PATH} S-1.7", milestone="later"),
        spec_node(4, labels=("status:backlog",)),
    ]
    assert sprint_state.spec_gaps(nodes, SPEC_FILES) == [
        {"path": None, "line": None, "message": message}
        for message in [
            "#2 has no spec line (אפיון: docs/specs/<repo>.md S-<n>.<m>)",
            f"#3 points at {SPEC_PATH} S-1.7: no such part",
        ]
    ]


def test_spec_gaps_open_part_without_an_issue():
    assert sprint_state.spec_gaps([], SPEC_FILES) == [OPEN_PART]


@pytest.mark.parametrize("flag", [["--spec"], []])
def test_main_spec_gaps_only_with_the_flag(flag, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pipeline_shas, "PIPELINE_URL", str(tmp_path / "missing"))
    monkeypatch.setattr(sprint_state, "CACHE", tmp_path / "cache.git")
    fake_github(monkeypatch, [spec_node(1)])
    monkeypatch.setattr(sprint_state, "repo_specs", lambda base: SPEC_FILES)
    sprint_state.main(flag)
    result = json.loads(capsys.readouterr().out)
    if flag:
        no_line = "#1 has no spec line (אפיון: docs/specs/<repo>.md S-<n>.<m>)"
        assert result["spec_gaps"] == [
            {"path": None, "line": None, "message": no_line},
            OPEN_PART,
        ]
    else:
        assert "spec_gaps" not in result


def test_specs_not_read_is_one_gap_and_the_check_goes_on(monkeypatch):
    def broken(base):
        raise ValueError("unknown revision origin/main")

    monkeypatch.setattr(sprint_state, "repo_specs", broken)
    assert sprint_state.spec_gaps_or_warning([], "main") == [
        {
            "path": None,
            "line": None,
            "message": "spec files not read: unknown revision origin/main",
        }
    ]


# S-1.3 (#295): paused issues, and the new order of dispatch.


def test_a_paused_issue_is_not_dispatched_and_is_listed_apart():
    result = run(
        node(1, labels=("task", "paused")),
        node(2, labels=("task", "costs-money")),
        node(3),
    )
    assert numbers(result["dispatch"]) == [3]
    assert result["paused"] == [1]
    assert result["on_hold"] == [2]


def test_what_waits_on_a_paused_issue_names_it():
    result = run(
        node(1, labels=("task", "paused"), blocking=[2]),
        node(2, blocked_by=[(1, "OPEN")]),
    )
    assert result["blocked"] == [
        {"number": 2, "blocked_by": [1], "outside_blockers": [], "paused_blockers": [1]}
    ]


def test_dispatch_follows_the_new_order():
    """A sub-issue of a started umbrella first, then fewest waiting."""
    result = run(
        node(1, blocking=[4, 5]),
        node(2),
        node(3),
        node(4, blocked_by=[(1, "OPEN")]),
        node(5, blocked_by=[(1, "OPEN")]),
        node(10, status="explore", subs=[3], closed_subs=[9]),
    )
    assert numbers(result["dispatch"]) == [3, 2, 1]


def test_an_issue_both_paused_and_costing_money_is_only_paused():
    result = run(node(1, labels=("task", "paused", "costs-money")))
    assert result["paused"] == [1]
    assert result["on_hold"] == []


def spec_pr(number, state="open", questions="_אין._"):
    return {
        "number": number,
        "state": state,
        "branch": f"claude/spec-{number}",
        "body": f"Refs #1\n\n### שאלות פתוחות\n{questions}\n",
        "headSha": f"sha{number}",
    }


def test_a_proposal_gets_a_spec_child_before_a_repair_and_a_bug():
    result = run(
        node(1, "needs-repair"),
        node(2, "ready-to-execute", labels=("bug",)),
        node(3, "backlog"),
    )
    assert numbers(result["dispatch"]) == [3, 1, 2]
    spec = result["dispatch"][0]
    assert spec["status"] == "spec"
    assert spec["prompt"] == "תכתוב אפיון ל-#3"
    assert result["proposals"] == [
        {"number": 3, "title": "issue 3", "stage": "waiting", "pr": None}
    ]


def test_a_second_proposal_waits_for_the_spec_child_with_the_spec_file():
    result = run(node(3, "backlog"), node(4, "backlog"))
    assert numbers(result["dispatch"]) == [3]
    assert result["held_by_overlap"] == [{"number": 4, "with": [3], "files": [SPEC]}]


def test_a_proposal_a_child_writes_holds_the_next_one():
    result = run(node(3, "backlog"), node(4, "backlog"), claimed=[3])
    assert result["dispatch"] == []
    assert result["held_by_overlap"] == [{"number": 4, "with": [3], "files": [SPEC]}]
    assert [p["stage"] for p in result["proposals"]] == ["writing", "waiting"]


def test_a_spec_pr_ready_for_review_is_in_the_merge_queue():
    result = run(
        node(3, "backlog"),
        node(4, "backlog"),
        status_of=clean,
        spec_prs={3: [spec_pr(40)], 4: [spec_pr(41, questions="- [ ] which?")]},
    )
    assert [p["stage"] for p in result["proposals"]] == ["review", "questions"]
    assert result["dispatch"] == []
    assert result["merge_queue"] == [
        {
            "number": 3,
            "pr": 40,
            "head_sha": "sha40",
            "kind": "spec",
            "mergeable_state": "clean",
            "ci": "success",
            "overlaps": [{"number": 4, "files": [SPEC]}],
        }
    ]


def test_a_merged_spec_waits_for_its_breakdown():
    result = run(node(3, "backlog"), spec_prs={3: [spec_pr(40, "merged")]})
    assert result["proposals"][0]["stage"] == "breakdown"
    assert result["dispatch"] == [] and result["merge_queue"] == []


def test_a_task_that_touches_only_the_spec_file_is_not_held():
    result = run(
        node(1, "ready-to-execute", files=[SPEC, "a.py"]),
        node(2, "ready-to-execute", files=[SPEC, "b.py"]),
        node(3, "backlog"),
    )
    assert numbers(result["dispatch"]) == [3, 1, 2]
    assert result["held_by_overlap"] == []


def test_a_sprint_with_no_proposal_has_the_same_dispatch_as_before():
    nodes = [node(1, "needs-repair"), node(2, "explore", files=["a.py"])]
    before = sprint_state.state(nodes, "W1", [], no_pr_status)
    assert before["proposals"] == []
    assert run(*nodes) == before
