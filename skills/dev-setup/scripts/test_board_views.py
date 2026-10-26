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


def milestone(title, open_issues):
    return {"title": title, "issues": {"totalCount": open_issues}}


def fake_gh(
    monkeypatch,
    views,
    milestones=None,
    columns=("Status",),
):
    """Answer gh and GraphQL like a board with these views; record each mutation."""
    if milestones is None:
        milestones = (milestone("M1", 2), milestone("M2", 0))
    sent = []

    def run(*args):
        if args[:3] == ("gh", "repo", "view"):
            return 0, "acme/widgets"
        if args[:3] == ("gh", "variable", "get"):
            return 0, "7"
        return 1, ""

    def graphql(query, **variables):
        if query is board_views.MILESTONES_QUERY:
            return {"repository": {"milestones": {"nodes": list(milestones)}}}
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


def test_without_open_issues_the_first_open_milestone_is_used(monkeypatch):
    sent = fake_gh(
        monkeypatch, [DEFAULT, ALL], milestones=[milestone("M1", 0), milestone("M2", 0)]
    )
    board_views.main([])
    assert sent[0][1]["filter"] == 'milestone:"M1"'


def test_current_sprint_skips_finished_milestones(monkeypatch):
    sent = fake_gh(
        monkeypatch, [DEFAULT, ALL], milestones=[milestone("M1", 0), milestone("M2", 3)]
    )
    board_views.main([])
    assert sent[0][1]["filter"] == 'milestone:"M2"'


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
