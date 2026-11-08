"""The sprint view follows the current sprint (claude-config #17)."""

import json

import gh_api
import pytest
import sprint_view as sv


def sprint_view(filter_):
    return {"id": "V1", "name": "ספרינט נוכחי", "filter": filter_}


def test_finished_sprint_moves_the_filter():
    views = [{"id": "V0", "name": "הכל", "filter": None}, sprint_view('milestone:"M1"')]
    assert sv.sprint_view_change(views, "M2 - Launch") == (
        "V1",
        'milestone:"M2 - Launch"',
    )


def test_a_filter_already_on_the_sprint_is_left_alone():
    assert sv.sprint_view_change([sprint_view('milestone:"M1"')], "M1") is None


@pytest.mark.parametrize(
    "views, sprint",
    [
        ([sprint_view('milestone:"M1"')], None),  # no milestone has open issues
        (
            [{"id": "V0", "name": "View 1", "filter": 'milestone:"M1"'}],
            "M2",
        ),  # no sprint view
        ([sprint_view("label:bug")], "M2"),  # no milestone term to move
        ([sprint_view(None)], "M2"),
    ],
)
def test_nothing_to_move(views, sprint):
    assert sv.sprint_view_change(views, sprint) is None


def test_only_the_milestone_term_changes():
    change = sv.sprint_view_change(
        [sprint_view('label:bug milestone:"Sprint 1" -status:Done')], "Sprint 2"
    )
    assert change == ("V1", 'label:bug milestone:"Sprint 2" -status:Done')
    change = sv.sprint_view_change([sprint_view("milestone:Old")], "New")
    assert change == ("V1", 'milestone:"New"')


def open_item(milestone_number, title, is_pr=False):
    item = {
        "state": "open",
        "milestone": {"number": milestone_number, "title": title, "state": "open"},
    }
    return {**item, "pull_request": {}} if is_pr else item


def test_sync_sprint_view_sends_the_update(monkeypatch):
    # M1 holds only an open PR, on the second page: the sprint is M2 (#164).
    pages = [[open_item(2, "M2")], [open_item(1, "M1", is_pr=True)]]
    calls, sent = [], []
    monkeypatch.setattr(
        gh_api, "gh", lambda *args: calls.append(args) or json.dumps(pages)
    )
    monkeypatch.setattr(gh_api, "graphql", lambda query, **kw: sent.append(kw))
    moved_to = sv.sync_sprint_view("dolev2/example", [sprint_view('milestone:"M1"')])
    assert sent == [{"view": "V1", "filter": 'milestone:"M2"'}]
    assert moved_to == 'milestone:"M2"'
    assert "--paginate" in calls[0] and "--slurp" in calls[0]
