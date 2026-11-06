"""The board sync's rules: what is written to the board, and which issues take part."""

from collections.abc import Iterator

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


@pytest.mark.parametrize(
    "from_labels, on_board, expected",
    [
        # A label the board does not show yet is written.
        ({"status": "done"}, {"status": "explore"}, {"status": "done"}),
        # A card dragged by hand goes back to its label (#111).
        ({"status": "explore"}, {"status": "done"}, {"status": "explore"}),
        # A blank board takes every label.
        (
            {"status": "explore", "area": "infra"},
            {},
            {"status": "explore", "area": "infra"},
        ),
        # A board that already agrees is not written.
        ({"status": "explore"}, {"status": "explore"}, {}),
        # A dimension with no label keeps the board's value.
        ({"status": "explore"}, {"status": "explore", "area": "infra"}, {}),
        ({}, {"status": "done"}, {}),
    ],
)
def test_the_board_takes_the_labels(from_labels, on_board, expected):
    assert sync_rules.board_changes(from_labels, on_board) == expected


@pytest.mark.parametrize(
    "labels, on_board, expected",
    [
        # Opened from the board: the card's column becomes its labels (WayOut #98).
        ([], {"status": "backlog"}, {"status": "backlog"}),
        # An area label it already has is kept over the card's.
        (
            ["area:infra"],
            {"status": "backlog", "area": "both"},
            {"status": "backlog", "area": "infra"},
        ),
        # With a status label the labels rule, whatever the card shows.
        (["status:explore"], {"status": "done"}, {}),
        # A decision has no status by design: its old column is not copied back
        # (claude-config #128).
        (["decision"], {"status": "ready-to-execute"}, {}),
        # A card with no status gives nothing.
        ([], {}, {}),
        ([], {"area": "infra"}, {}),
    ],
)
def test_an_issue_without_a_status_takes_its_card_once(labels, on_board, expected):
    sync_rules.resolve_options({"Area": field("Area", "Infra", "Both")})
    assert sync_rules.labels_from_board(labels, on_board) == expected


def test_label_edit_keeps_labels_outside_the_dimensions():
    labels = ["task", "status:explore", "area:infra"]
    winner = {"status": "done", "area": "infra"}
    assert sync_rules.label_edit_args(labels, winner) == [
        "--add-label",
        "status:done",
        "--remove-label",
        "status:explore",
    ]
    unchanged = {"status": "explore", "area": "infra"}
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
    assert sync_rules.labels_state(["area:backend", "status:explore"]) == {
        "status": "explore"
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
        ["status:explore", "status:done", "area:infra"]
    ) == ["status"]
    assert sync_rules.doubled_dimensions(["status:explore", "task", "area:infra"]) == []


@pytest.mark.parametrize(
    "labels, state, on_board, expected",
    [
        (["status:explore"], "OPEN", False, True),
        ([], "OPEN", True, True),  # opened from the board (WayOut #98, #55)
        ([], "OPEN", False, False),  # not a pipeline issue
        (["decision"], "OPEN", False, True),  # no status, still pipeline
        (["status:backlog"], "CLOSED", True, False),  # closed as not-planned
        ([], "CLOSED", True, False),
        (["status:done"], "CLOSED", True, True),
    ],
)
def test_which_issues_are_synced(labels, state, on_board, expected):
    assert sync_rules.should_sync(labels, state, on_board) is expected


@pytest.mark.parametrize(
    "labels, state, reason, expected",
    [
        (["task", "status:in-review"], "CLOSED", "COMPLETED", True),  # #97
        (["status:backlog"], "CLOSED", "COMPLETED", True),
        (["status:backlog"], "CLOSED", "NOT_PLANNED", False),
        (["status:done"], "CLOSED", "COMPLETED", False),
        (["status:in-review"], "OPEN", None, False),
        (["task"], "CLOSED", "COMPLETED", False),  # not a pipeline issue
        (["decision"], "CLOSED", "COMPLETED", True),
    ],
)
def test_which_closed_issues_need_status_done(labels, state, reason, expected):
    assert sync_rules.needs_done_label(labels, state, reason) is expected


def test_done_labels_replace_the_status_and_keep_the_rest():
    assert sync_rules.done_labels(["task", "area:infra", "status:in-review"]) == [
        "task",
        "area:infra",
        "status:done",
    ]


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


@pytest.mark.parametrize(
    "labels, on_board, expected",
    [
        # claude-config #128: a task turned decision keeps its old column on the card.
        (["decision"], {"status": "ready-to-execute"}, True),
        (["decision", "area:infra"], {"status": "explore", "area": "infra"}, True),
        # The card already sits in no column: nothing to clear.
        (["decision"], {}, False),
        (["decision"], {"area": "infra"}, False),
        # A status label rules, decision or not.
        (["decision", "status:explore"], {"status": "done"}, False),
        # Not a decision: the card is the one exception of an issue opened from it.
        ([], {"status": "backlog"}, False),
    ],
)
def test_a_decision_card_loses_its_column(labels, on_board, expected):
    assert sync_rules.clears_status(labels, on_board) is expected
