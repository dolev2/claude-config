"""board_views.py: which views it creates or converts, and what it leaves alone."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "board_views.py"
spec = importlib.util.spec_from_file_location("board_views", SCRIPT)
board_views = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board_views)

FIELDS = [
    "Title",
    "Assignees",
    "Status",
    "Labels",
    "Linked pull requests",
    "Milestone",
    "Sub-issues progress",
]
DEFAULT = {"id": "V1", "name": "View 1", "layout": "TABLE_LAYOUT", "filter": None}
SPRINT = {
    "id": "V2",
    "name": "ספרינט נוכחי",
    "layout": "BOARD_LAYOUT",
    "filter": 'milestone:"M1"',
}
ALL = {"id": "V3", "name": "הכל", "layout": "TABLE_LAYOUT", "filter": None}


def milestone(number, title=None):
    return {"number": number, "title": title or f"M{number}", "state": "open"}


def issue(ms, pull_request=False):
    """An open REST item in milestone `ms` (a milestone() dict, or None)."""
    item = {"number": 100, "state": "open", "milestone": ms}
    if pull_request:
        item["pull_request"] = {"url": "https://api.github.com/x"}
    return item


def fake_gh(
    monkeypatch,
    views,
    milestones=None,
    issues=None,
    columns=("Status",),
    calls=None,
):
    """Answer gh, REST and GraphQL like a board with these views; record each mutation.

    By default M1 has an open issue and M2 has none. `calls`, when given, collects
    every command run and every GraphQL query sent, in order.
    """
    if milestones is None:
        milestones = [milestone(1), milestone(2)]
    if issues is None:
        issues = [issue(milestones[0])] if milestones else []
    calls = [] if calls is None else calls
    sent = []

    def run(*args):
        calls.append(args)
        if args[:3] == ("gh", "variable", "get"):
            return 0, "7"
        return 1, ""

    def api_list(path):
        calls.append(("rest", path))
        if path.startswith("repos/acme/widgets/milestones?state=open"):
            return list(milestones)
        if path.startswith("repos/acme/widgets/issues?state=open"):
            return list(issues)
        raise AssertionError(f"unexpected REST call {path}")

    def graphql(query, **variables):
        calls.append(("graphql", query))
        if query is board_views.BOARD_QUERY:
            group = {"nodes": [{"name": c} for c in columns]}
            # After a write, the read-back shows the board as the script left it.
            nodes = [
                {**v, "verticalGroupByFields": group}
                for v in ([SPRINT, ALL] if sent else views)
            ]
            return {
                "user": {
                    "projectV2": {
                        "id": "P1",
                        "title": "Widgets",
                        "fields": {
                            "nodes": [{"id": f"F-{f}", "name": f} for f in FIELDS]
                        },
                        "views": {"nodes": nodes},
                    }
                }
            }
        sent.append((query, variables))
        if query is board_views.CREATE:
            return {
                "createProjectV2View": {
                    "projectV2View": {"id": f"NEW-{variables['name']}"}
                }
            }
        return {"updateProjectV2View": {"projectV2View": {"id": variables["view"]}}}

    monkeypatch.setattr(board_views, "run", run)
    monkeypatch.setattr(board_views, "graphql", graphql)
    monkeypatch.setattr(board_views.gh_rest, "api_list", api_list)
    monkeypatch.setattr(board_views.gh_rest, "current_repo", lambda: "acme/widgets")
    return sent


def ids(names):
    return [f"F-{n}" for n in names]


def test_default_view_becomes_the_sprint_view(monkeypatch):
    sent = fake_gh(monkeypatch, [DEFAULT])
    board_views.main([])
    assert sent == [
        (
            board_views.UPDATE,
            {
                "view": "V1",
                "name": "ספרינט נוכחי",
                "layout": "BOARD_LAYOUT",
                "filter": 'milestone:"M1"',
                "fields": ids(board_views.SPRINT_FIELDS),
            },
        ),
        (
            board_views.CREATE,
            {
                "project": "P1",
                "name": "הכל",
                "layout": "TABLE_LAYOUT",
                "fields": ids(board_views.ALL_FIELDS),
            },
        ),
    ]


def test_empty_board_gets_both_views_and_the_filter(monkeypatch):
    sent = fake_gh(monkeypatch, [])
    board_views.main([])
    assert [(q, v.get("name"), v.get("filter")) for q, v in sent] == [
        (board_views.CREATE, "ספרינט נוכחי", None),
        (board_views.UPDATE, None, 'milestone:"M1"'),
        (board_views.CREATE, "הכל", None),
    ]
    assert sent[1][1]["view"] == "NEW-ספרינט נוכחי"


def test_configured_board_is_left_alone(monkeypatch, capsys):
    sent = fake_gh(monkeypatch, [SPRINT, ALL])
    board_views.main([])
    assert sent == []
    assert "nothing to do" in capsys.readouterr().out


def test_other_views_are_not_touched(monkeypatch):
    custom = {"id": "V9", "name": "By area", "layout": "TABLE_LAYOUT", "filter": None}
    sent = fake_gh(monkeypatch, [custom, ALL])
    board_views.main([])
    assert [q for q, _ in sent] == [board_views.CREATE, board_views.UPDATE]
    assert all(v.get("view") != "V9" for _, v in sent)


def test_a_filtered_default_view_is_not_converted(monkeypatch):
    sent = fake_gh(monkeypatch, [{**DEFAULT, "filter": "label:bug"}, ALL])
    board_views.main([])
    assert sent[0][0] is board_views.CREATE


def test_a_full_run_reads_the_repo_and_milestones_over_rest(monkeypatch):
    """GraphQL carries only the board; no `gh repo view` (claude-config #283)."""
    calls = []
    fake_gh(monkeypatch, [DEFAULT], calls=calls)
    board_views.main([])
    board_queries = {board_views.BOARD_QUERY, board_views.CREATE, board_views.UPDATE}
    graphql = [c[1] for c in calls if c[0] == "graphql"]
    assert graphql and all(q in board_queries for q in graphql)
    assert not any(c[:3] == ("gh", "repo", "view") for c in calls)
    rest = [c[1] for c in calls if c[0] == "rest"]
    assert any(path.startswith("repos/acme/widgets/milestones") for path in rest)


def test_without_open_issues_the_first_open_milestone_is_used(monkeypatch):
    sent = fake_gh(
        monkeypatch,
        [DEFAULT, ALL],
        milestones=[milestone(5), milestone(3)],
        issues=[],
    )
    board_views.main([])
    assert sent[0][1]["filter"] == 'milestone:"M3"'


def test_current_sprint_skips_finished_milestones(monkeypatch):
    m1, m2 = milestone(1), milestone(2)
    sent = fake_gh(monkeypatch, [DEFAULT, ALL], milestones=[m1, m2], issues=[issue(m2)])
    board_views.main([])
    assert sent[0][1]["filter"] == 'milestone:"M2"'


def test_a_milestone_with_only_an_open_pr_is_not_the_sprint(monkeypatch):
    m1, m2 = milestone(1), milestone(2)
    sent = fake_gh(
        monkeypatch,
        [DEFAULT, ALL],
        milestones=[m1, m2],
        issues=[issue(m1, pull_request=True), issue(m2)],
    )
    board_views.main([])
    assert sent[0][1]["filter"] == 'milestone:"M2"'


def test_an_explicit_sprint_skips_the_issue_read(monkeypatch):
    calls = []
    sent = fake_gh(monkeypatch, [DEFAULT, ALL], calls=calls)
    board_views.main(["--sprint", "M2"])
    assert sent[0][1]["filter"] == 'milestone:"M2"'
    assert not any(c[0] == "rest" and "/issues" in c[1] for c in calls)


def test_no_milestones_stops_before_writing(monkeypatch):
    sent = fake_gh(monkeypatch, [DEFAULT], milestones=[])
    with pytest.raises(SystemExit, match="no open milestone"):
        board_views.main([])
    assert sent == []


def test_unknown_sprint_stops_before_writing(monkeypatch):
    sent = fake_gh(monkeypatch, [DEFAULT])
    with pytest.raises(SystemExit, match="not an open milestone"):
        board_views.main(["--sprint", "M9"])
    assert sent == []


def test_dry_run_sends_nothing(monkeypatch, capsys):
    sent = fake_gh(monkeypatch, [DEFAULT])
    board_views.main(["--dry-run"])
    assert sent == []
    assert "would: " in capsys.readouterr().out


def test_missing_columns_are_reported(monkeypatch, capsys):
    fake_gh(monkeypatch, [DEFAULT], columns=())
    board_views.main([])
    assert "Column by: Status" in capsys.readouterr().out
