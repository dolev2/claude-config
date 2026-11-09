"""sprint_state.py: the sprint as one JSON object, for the sprint orchestrator."""

import importlib.util
import json
import subprocess
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
    closed_subs=(),
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
        "subIssues": {
            "nodes": [{"number": n, "state": "OPEN"} for n in subs]
            + [{"number": n, "state": "CLOSED"} for n in closed_subs]
        },
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


def test_an_umbrella_whose_subs_are_all_closed_is_dispatched():
    result = run(node(1, closed_subs=[5, 6]))
    assert numbers(result["dispatch"]) == [1]
    assert result["umbrellas"] == []


def test_an_umbrella_with_an_open_sub_is_listed_apart():
    result = run(node(1, subs=[6], closed_subs=[5]), node(2, "done", subs=[7]))
    assert result["dispatch"] == []
    assert result["umbrellas"] == [{"number": 1, "open_subs": [6]}]


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


def sh(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    """A local git repo standing in for the pipeline's remote; commit(path) adds one."""
    remote = tmp_path / "remote"
    remote.mkdir()
    sh(remote, "init", "-q", "-b", "main")
    sh(remote, "config", "user.email", "t@example.com")
    sh(remote, "config", "user.name", "t")
    monkeypatch.setattr(sprint_state, "PIPELINE_URL", str(remote))
    monkeypatch.setattr(sprint_state, "CACHE", tmp_path / "cache.git")

    def commit(path):
        file = remote / path
        if not file.suffix:
            file.mkdir(exist_ok=True)
            file = file / "f.md"
        file.write_text(file.read_text() + "x" if file.exists() else "x")
        sh(remote, "add", "-A")
        sh(remote, "commit", "-q", "-m", path)
        out = subprocess.run(
            ["git", "-C", str(remote), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()

    return commit


def fake_github(monkeypatch, nodes):
    monkeypatch.setattr(sprint_state, "current_repo", lambda: "acme/widgets")
    monkeypatch.setattr(sprint_state, "open_issue_nodes", lambda repo, with_body: nodes)


def shas(monkeypatch, capsys):
    fake_github(monkeypatch, [node(1)])
    sprint_state.main([])
    result = json.loads(capsys.readouterr().out)
    return result["pipeline_sha"], result["session_sha"]


@pytest.mark.parametrize(
    ("changed", "group"),
    [("rules", 1), ("settings.json", 1), ("skills", 0), ("hooks", 0)],
)
def test_a_merge_moves_only_the_sha_of_its_group(
    pipeline, monkeypatch, capsys, changed, group
):
    first = [pipeline("skills"), pipeline("CLAUDE.md")]
    assert list(shas(monkeypatch, capsys)) == first

    new = pipeline(changed)
    second = list(shas(monkeypatch, capsys))
    assert second[group] == new
    assert second[1 - group] == first[1 - group]


def test_a_merge_outside_both_groups_moves_neither(pipeline, monkeypatch, capsys):
    """A one-commit clone would name this commit for both: the trap of ~/.claude."""
    first = [pipeline("skills"), pipeline("rules")]
    pipeline("README.md")
    assert list(shas(monkeypatch, capsys)) == first


def test_a_group_without_commits_is_null(pipeline, monkeypatch, capsys):
    sha = pipeline("hooks")
    assert shas(monkeypatch, capsys) == (sha, None)


def test_a_failing_git_leaves_null_shas_and_the_rest_of_the_state(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(sprint_state, "PIPELINE_URL", str(tmp_path / "missing"))
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
