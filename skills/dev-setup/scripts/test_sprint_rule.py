"""sprint_rule.py: the one rule for the current sprint, and its copy for the board."""

from pathlib import Path

import pytest
from sprint_rule import current_sprint

HERE = Path(__file__).resolve().parent
COPY = HERE.parent / "actions" / "project-sync" / "sprint_rule.py"


def item(milestone_number, title="", state="open", milestone_state="open", pr=False):
    """An open issue (or PR) as REST returns it, in milestone `milestone_number`."""
    milestone = (
        {
            "number": milestone_number,
            "title": title or f"M{milestone_number}",
            "state": milestone_state,
        }
        if milestone_number
        else None
    )
    found = {"state": state, "milestone": milestone}
    return {**found, "pull_request": {}} if pr else found


def test_the_lowest_open_milestone_with_an_open_issue():
    assert current_sprint([item(3), item(2), item(None)]) == "M2"


def test_a_milestone_with_only_an_open_pr_is_not_the_sprint():
    # GitHub's milestone.open_issues counts the PR, so pipeline_info.py and the sprint
    # view used to point here while rank_issues.py pointed at M2 (#164).
    assert current_sprint([item(1, pr=True), item(2)]) == "M2"


@pytest.mark.parametrize(
    "issues",
    [
        [],
        [item(None)],
        [item(1, pr=True)],
        [item(1, state="closed")],
        [item(1, milestone_state="closed")],
    ],
)
def test_no_sprint(issues):
    assert current_sprint(issues) is None


def test_graphql_shaped_nodes_count_too():
    # gh_rest.py nodes: no `state` of their own, the milestone state in capitals.
    node = {"milestone": {"number": 4, "title": "W4", "state": "OPEN"}}
    assert current_sprint([node]) == "W4"


def test_the_board_sync_carries_an_identical_copy():
    # The board sync is downloaded as a flat folder, so it keeps its own copy.
    assert COPY.read_bytes() == (HERE / "sprint_rule.py").read_bytes(), (
        "actions/project-sync/sprint_rule.py differs from scripts/sprint_rule.py: "
        "copy the scripts version over it"
    )
