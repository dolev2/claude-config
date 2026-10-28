"""The sprint view follows the current sprint (claude-config #17)."""

import gh_api
import pytest
import sprint_view as sv


def milestone(number, title, open_issues):
    return {"number": number, "title": title, "open_issues": open_issues}


def sprint_view(filter_):
    return {"id": "V1", "name": "ספרינט נוכחי", "filter": filter_}


def test_current_sprint_is_the_first_milestone_with_open_issues():
    milestones = [milestone(3, "M3", 1), milestone(1, "M1", 0), milestone(2, "M2", 4)]
    assert sv.current_sprint(milestones) == "M2"
    assert sv.current_sprint([milestone(1, "M1", 0)]) is None


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


def test_sync_sprint_view_sends_the_update(monkeypatch):
    sent = []
    monkeypatch.setattr(
        gh_api,
        "gh",
        lambda *args: (
            '[{"number": 1, "title": "M1", "open_issues": 0},'
            ' {"number": 2, "title": "M2", "open_issues": 2}]'
        ),
    )
    monkeypatch.setattr(gh_api, "graphql", lambda query, **kw: sent.append(kw))
    moved_to = sv.sync_sprint_view("dolev2/example", [sprint_view('milestone:"M1"')])
    assert sent == [{"view": "V1", "filter": 'milestone:"M2"'}]
    assert moved_to == 'milestone:"M2"'
