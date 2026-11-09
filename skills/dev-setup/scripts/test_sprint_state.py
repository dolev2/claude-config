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


def body(files=()):
    bullets = "\n".join(f"- `{f}`: changes" for f in files)
    return (
        "### מה רוצים\n\ngoal\n\n### הקשר / קישורים\n\ncontext\n\n---\n"
        f"### Plan\n\n##### קבצים שצפויים להשתנות\n{bullets}\n\n"
        "### שאלות פתוחות\n\n_אין שאלות פתוחות._\n"
    )


def node(
    number,
    status="ready-to-execute",
    files=(),
    blocked_by=(),
    blocking=(),
    labels=("task",),
    subs=(),
    prs=(),
    milestone="W1",
):
    names = [f"status:{status}", *labels]
    return {
        "number": number,
        "title": f"issue {number}",
        "body": body(files),
        "labels": {"nodes": [{"name": name} for name in names]},
        "milestone": {"number": 1, "title": milestone, "state": "OPEN"},
        "blockedBy": {"nodes": [{"number": n, "state": s} for n, s in blocked_by]},
        "blocking": {"nodes": [{"number": n, "state": "OPEN"} for n in blocking]},
        "closedByPullRequestsReferences": {"totalCount": len(prs)},
        "closingPullRequests": [{"number": p, "headSha": f"sha{p}"} for p in prs],
        "parent": None,
        "subIssues": {"nodes": [{"number": n} for n in subs]},
    }


def no_pr_status(pr):
    raise AssertionError(f"PR {pr['number']} should not be read")


def run(*nodes, claimed=(), status_of=no_pr_status):
    return sprint_state.state(list(nodes), "W1", list(claimed), status_of)


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
        node(1, "backlog"),
        node(1, "done"),
        node(1, "waiting-approval"),
    ],
    ids=["blocked", "costs-money", "umbrella", "backlog", "done", "dolev-turn"],
)
def test_what_is_never_dispatched(issue):
    assert run(issue)["dispatch"] == []


def test_a_closed_blocker_does_not_block():
    assert numbers(run(node(1, blocked_by=[(9, "CLOSED")]))["dispatch"]) == [1]


def test_blocked_and_on_hold_are_listed_apart():
    result = run(
        node(1, blocked_by=[(9, "OPEN")]), node(2, labels=("task", "costs-money"))
    )
    assert result["blocked"] == [
        {"number": 1, "blocked_by": [9], "outside_blockers": []}
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
        }
    ]
    assert seen == [{"number": 40, "headSha": "sha40"}]


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
    assert sprint_state.ci_summary(runs) == summary


def commit(sha, date):
    return {"sha": sha, "commit": {"committer": {"date": date}}}


def fake_api(newest_by_path):
    """api() for the commits endpoint: the newest commit of each path, or none."""

    def api(path):
        asked = path.split("path=")[1].split("&")[0]
        found = newest_by_path.get(asked)
        return [found] if found else []

    return api


def fake_github(monkeypatch, nodes, newest_by_path=None):
    monkeypatch.setattr(sprint_state, "current_repo", lambda: "acme/widgets")
    monkeypatch.setattr(sprint_state, "open_issue_nodes", lambda repo, with_body: nodes)
    if newest_by_path is None:
        newest_by_path = {
            "skills": commit("abc123", "2026-11-01T10:00:00Z"),
            "CLAUDE.md": commit("def456", "2026-11-01T09:00:00Z"),
        }
    monkeypatch.setattr(sprint_state, "api", fake_api(newest_by_path))


OLD = commit("old", "2026-11-01T10:00:00Z")
NEW = commit("new", "2026-11-02T10:00:00Z")


def test_a_group_takes_the_newest_commit_even_from_a_later_path(monkeypatch):
    monkeypatch.setattr(sprint_state, "api", fake_api({"skills": OLD, "hooks": NEW}))
    assert sprint_state.last_commit(["skills", "hooks"]) == "new"


@pytest.mark.parametrize(
    ("changed", "moved", "stayed"),
    [
        ("rules", "session_sha", "pipeline_sha"),
        ("settings.json", "session_sha", "pipeline_sha"),
        ("skills", "pipeline_sha", "session_sha"),
        ("hooks", "pipeline_sha", "session_sha"),
    ],
)
def test_a_merge_moves_only_the_sha_of_its_group(
    monkeypatch, capsys, changed, moved, stayed
):
    before = {"skills": OLD, "CLAUDE.md": OLD}
    fake_github(monkeypatch, [node(1)], before)
    sprint_state.main([])
    first = json.loads(capsys.readouterr().out)

    fake_github(monkeypatch, [node(1)], before | {changed: NEW})
    sprint_state.main([])
    second = json.loads(capsys.readouterr().out)

    assert second[moved] == "new" and first[moved] == "old"
    assert second[stayed] == first[stayed] == "old"


def test_a_path_without_commits_does_not_fail(monkeypatch):
    monkeypatch.setattr(sprint_state, "api", fake_api({"rules": OLD}))
    assert sprint_state.last_commit(["CLAUDE.md", "rules"]) == "old"
    assert sprint_state.last_commit(["settings.json"]) is None


def test_main_prints_the_state_with_both_shas(monkeypatch, capsys):
    fake_github(monkeypatch, [node(1), node(2)])
    sprint_state.main(["--claimed", "1"])
    result = json.loads(capsys.readouterr().out)
    assert numbers(result["dispatch"]) == [2]
    assert result["pipeline_sha"] == "abc123"
    assert result["session_sha"] == "def456"


def test_main_without_an_open_milestone_exits(monkeypatch):
    fake_github(monkeypatch, [])
    with pytest.raises(SystemExit, match="No open milestone"):
        sprint_state.main([])


def test_claimed_that_is_not_numbers_is_a_usage_error(monkeypatch):
    fake_github(monkeypatch, [node(1)])
    with pytest.raises(SystemExit) as exit_info:
        sprint_state.main(["--claimed", "abc"])
    assert exit_info.value.code == 2
