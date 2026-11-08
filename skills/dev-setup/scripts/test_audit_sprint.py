"""audit_sprint.py: the sprint-wide check of "Blocked by" links that dev-next runs."""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("audit_sprint", HERE / "audit_sprint.py")
audit_sprint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_sprint)


def body(goal="", context="", files=()):
    bullets = "\n".join(f"- `{f}`: changes" for f in files)
    return (
        f"### מה רוצים\n\n{goal}\n\n### הקשר / קישורים\n\n{context}\n\n---\n"
        f"### Plan\n\n#### פירוט טכני\n\n##### הגישה\nsteps\n\n"
        f"##### קבצים שצפויים להשתנות\n{bullets}\n\n##### בדיקות\n- `not/a/file.py`\n\n"
        "### שאלות פתוחות\n\n_אין שאלות פתוחות._\n"
    )


def node(number, text="", blocked_by=(), has_pr=False, parent=None, subs=()):
    return {
        "number": number,
        "title": f"issue {number}",
        "body": text or body(),
        "labels": {"nodes": [{"name": "status:explore"}]},
        "milestone": {"number": 1, "title": "W1", "state": "OPEN"},
        "blockedBy": {"nodes": [{"number": n, "state": s} for n, s in blocked_by]},
        "blocking": {"nodes": []},
        "closedByPullRequestsReferences": {"totalCount": 1 if has_pr else 0},
        "parent": {"number": parent} if parent else None,
        "subIssues": {"nodes": [{"number": n} for n in subs]},
    }


def lines(*nodes):
    issues = [audit_sprint.sprint_issue(n) for n in nodes]
    return [f.line() for f in audit_sprint.audit(issues)]


def test_a_line_without_a_link_and_a_link_without_a_line():
    found = lines(
        node(1, body(context="תלוי ב: #2.")),
        node(2, body(context="תלוי ב: אין."), blocked_by=[(3, "CLOSED")]),
        node(3),
    )
    assert found == [
        "LINE-MISMATCH #1: line #2, links none",
        "LINE-MISMATCH #2: line none, links #3",
    ]


def test_a_closed_blocker_still_matches_the_line():
    assert lines(node(1, body(context="תלוי ב: #9."), blocked_by=[(9, "CLOSED")])) == []


def test_an_open_blocker_outside_the_sprint():
    assert lines(node(1, blocked_by=[(9, "OPEN")])) == ["OUTSIDE #1 -> #9"]


def test_a_cycle_is_reported_once():
    found = lines(node(1, blocked_by=[(2, "OPEN")]), node(2, blocked_by=[(1, "OPEN")]))
    assert found == ["CYCLE #1 #2"]


def test_a_mention_without_a_link():
    found = lines(node(1, body(goal="builds on what #3 adds")), node(3))
    assert found == ["MENTION #1 -> #3"]


def test_a_linked_or_outside_mention_is_not_a_finding():
    linked = node(1, body(goal="builds on #3"), blocked_by=[(3, "OPEN")])
    assert lines(linked, node(3)) == []
    assert lines(node(1, body(goal="like #40 in another repo, and owner/x#3"))) == []


def test_an_umbrella_naming_its_sub_issues_is_not_a_mention():
    umbrella = node(1, body(goal="- [ ] #2 the first part"), subs=[2])
    part = node(2, body(context="part of #1"), parent=1)
    assert lines(umbrella, part) == []


def test_overlapping_plans_are_a_merge_candidate_before_any_pr():
    found = lines(node(1, body(files=["a.py", "b.py"])), node(2, body(files=["b.py"])))
    assert found == ["OVERLAP #1 #2: b.py  merge-candidate"]


def test_an_overlap_with_a_pr_is_not_a_merge_candidate():
    found = lines(
        node(1, body(files=["a.py"]), has_pr=True), node(2, body(files=["a.py"]))
    )
    assert found == ["OVERLAP #1 #2: a.py"]


def test_linked_overlap_is_not_a_finding():
    found = lines(
        node(1, body(files=["a.py"])),
        node(2, body(files=["a.py"]), blocked_by=[(1, "OPEN")]),
    )
    assert found == []


def test_only_the_files_section_counts():
    issue = audit_sprint.sprint_issue(node(1, body(files=["a.py"])))
    assert issue.files == {"a.py"}


def test_parallel_work_prefixes_are_not_files():
    parallel = (
        "##### עבודה במקביל\n- **שרת:** `backend/`\n- **מסכים:** `frontend/src/`\n\n"
    )
    text = body(files=["backend/api.py"]).replace(
        "##### קבצים", parallel + "##### קבצים"
    )
    issue = audit_sprint.sprint_issue(node(1, text))
    assert issue.files == {"backend/api.py"}


def test_a_clean_sprint_has_no_findings():
    assert lines(node(1), node(2, blocked_by=[(1, "OPEN")])) == []


def test_digest_carries_goal_and_files():
    nodes = [node(1, body(goal="the goal", files=["a.py"]))]
    issues = [audit_sprint.sprint_issue(n) for n in nodes]
    result = audit_sprint.digest("W1", issues, [])
    assert result["issues"][0]["goal"] == "the goal"
    assert result["issues"][0]["files"] == ["a.py"]


def test_digest_carries_findings_as_data():
    nodes = [node(1, body(files=["a.py"])), node(2, body(files=["a.py"]))]
    issues = [audit_sprint.sprint_issue(n) for n in nodes]
    digest = audit_sprint.digest("W1", issues, audit_sprint.audit(issues))
    [finding] = digest["findings"]
    assert finding == {
        "code": "OVERLAP",
        "numbers": [1, 2],
        "detail": "a.py  merge-candidate",
        "line": "OVERLAP #1 #2: a.py  merge-candidate",
    }
