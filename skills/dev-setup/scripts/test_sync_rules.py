"""The board sync's rules: who wins, which issues take part, and the marker."""

from collections.abc import Iterator

import marker
import pytest
import sync_rules


@pytest.fixture(autouse=True)
def default_board_options() -> Iterator[None]:
    """Reset what resolve_options fits to a board, so no test sees another's board."""
    sync_rules.resolve_options({})
    yield
    sync_rules.resolve_options({})


def field(name, *options):
    return {
        "id": name,
        "name": name,
        "options": [{"id": o, "name": o} for o in options],
    }


def test_marker_reads_and_writes_only_its_own_name():
    body = "text\n\n<!-- crm-sync: owner=claude status=explore -->\n"
    assert marker.read_marker(body, "crm-sync") == {
        "owner": "claude",
        "status": "explore",
    }
    assert marker.write_marker(body, {"status": "done"}, "crm-sync").endswith(
        "<!-- crm-sync: status=done -->\n"
    )
    assert marker.read_marker("<!-- wayout-sync: owner=claude -->", "crm-sync") == {}


def test_a_missing_marker_is_added_at_the_end():
    assert marker.write_marker("text\n\n", {"owner": "dolev"}, "x-sync") == (
        "text\n\n<!-- x-sync: owner=dolev -->\n"
    )


def test_blank_board_takes_the_labels_even_when_the_marker_matches():
    state = {"owner": "claude", "status": "explore"}
    assert sync_rules.choose_winner(state, state, {}) == (state, "labels")
    assert sync_rules.choose_winner(state, state, state) == (None, None)
    assert sync_rules.choose_winner({}, {}, {}) == (None, None)


def test_board_edit_wins_over_labels():
    previous = {"status": "explore"}
    on_board = {"status": "done"}
    assert sync_rules.choose_winner(previous, {"status": "backlog"}, on_board) == (
        on_board,
        "project",
    )


def test_label_edit_keeps_labels_outside_the_dimensions():
    labels = ["task", "status:explore", "owner:claude"]
    winner = {"status": "done", "owner": "claude"}
    assert sync_rules.label_edit_args(labels, winner) == [
        "--add-label",
        "status:done",
        "--remove-label",
        "status:explore",
    ]
    unchanged = {"status": "explore", "owner": "claude"}
    assert sync_rules.label_edit_args(labels, unchanged) == []


@pytest.mark.parametrize(
    "options, label, shown",
    [
        (("Backend", "Frontend", "Both", "Infra"), "area:both", "Both"),
        (("Design", "Content", "SEO", "Infra"), "area:seo", "SEO"),
        (("Engine", "Render", "Skills", "Methodology", "Web"), "area:engine", "Engine"),
    ],
)
def test_areas_are_read_from_the_board(options, label, shown):
    sync_rules.resolve_options({"Area": field("Area", *options)})
    assert sync_rules.labels_state([label]) == {"area": label.split(":")[1]}
    assert sync_rules.project_state({"Area": shown}) == {"area": label.split(":")[1]}


def test_an_area_the_board_lacks_is_left_out():
    sync_rules.resolve_options({"Area": field("Area", "Design", "Infra")})
    assert sync_rules.labels_state(["area:backend", "owner:claude"]) == {
        "owner": "claude"
    }


@pytest.mark.parametrize("board_name", ["Plan questions", "Plan questions (Dolev)"])
def test_plan_questions_matches_either_board_name(board_name):
    sync_rules.resolve_options(
        {"Status": field("Status", "Explore (Claude)", board_name, "Done")}
    )
    assert sync_rules.STATUS_OPTIONS["plan-questions"] == board_name
    assert sync_rules.project_state({"Status": board_name}) == {
        "status": "plan-questions"
    }


def test_two_labels_of_one_kind_are_reported():
    assert sync_rules.doubled_dimensions(
        ["status:explore", "status:done", "owner:claude"]
    ) == ["status"]
    assert (
        sync_rules.doubled_dimensions(["status:explore", "owner:claude", "area:infra"])
        == []
    )


@pytest.mark.parametrize(
    "labels, state, on_board, expected",
    [
        (["status:explore"], "OPEN", False, True),
        ([], "OPEN", True, True),  # opened from the board (WayOut #98, #55)
        ([], "OPEN", False, False),  # not a pipeline issue
        (["owner:dolev"], "CLOSED", True, False),  # closed as not-planned
        ([], "CLOSED", True, False),
        (["status:done"], "CLOSED", True, True),
    ],
)
def test_which_issues_are_synced(labels, state, on_board, expected):
    assert sync_rules.should_sync(labels, state, on_board) is expected


@pytest.mark.parametrize(
    "status, state, milestone, expected",
    [
        ("status:plan-questions", "OPEN", None, True),  # WayOut #42, #117
        ("status:explore", "OPEN", None, True),
        ("status:plan-questions", "OPEN", {"title": "Sprint 5"}, False),
        ("status:backlog", "OPEN", None, False),  # a backlog idea, on purpose
        ("status:done", "OPEN", None, False),
        ("status:explore", "CLOSED", None, False),
        (None, "OPEN", None, False),
    ],
)
def test_active_without_sprint(status, state, milestone, expected):
    issue = {"state": state, "milestone": milestone}
    labels = ["task"] + ([status] if status else [])
    assert sync_rules.is_active_without_sprint(issue, labels) is expected
