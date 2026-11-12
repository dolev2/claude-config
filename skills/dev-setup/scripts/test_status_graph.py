"""status_graph.py: the sprint's blocking graph for /status (S-1.48)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from status_graph import EMPTY, NO_SPRINT, OTHER_REPO, graph  # noqa: E402
from test_sprint_state import node  # noqa: E402


def status_he(status):
    return {"explore": "בתכנון", "ready-to-execute": "מוכן לקוד"}.get(
        status, status or "בלי סטטוס"
    )


def draw(nodes: list[dict], sprint: str | None = "W1") -> str:
    """The graph of `sprint`, from its issues in the given order."""
    in_sprint = [n for n in nodes if n["milestone"]["title"] == sprint]
    return graph(None if sprint is None else in_sprint, nodes, status_he)


def mermaid(text: str) -> list[str]:
    """The lines inside the Mermaid block."""
    block = text.split("```mermaid\n", 1)[1].split("```", 1)[0]
    return block.strip().splitlines()


def test_a_node_per_sprint_issue_with_its_status():
    lines = mermaid(draw([node(1, "explore"), node(2)]))
    assert lines[0] == "flowchart TD"
    assert '  n1["#1<br>issue 1<br>בתכנון"]' in lines
    assert '  n2["#2<br>issue 2<br>מוכן לקוד"]' in lines


def test_an_issue_without_blockers_has_no_arrow():
    lines = mermaid(draw([node(1), node(2)]))
    assert not [line for line in lines if "-->" in line]


def test_an_open_blocker_points_at_what_waits_for_it():
    nodes = [node(1), node(2, blocked_by=[(1, "OPEN")])]
    assert "  n1 --> n2" in mermaid(draw(nodes))


def test_a_closed_blocker_is_left_out():
    lines = mermaid(draw([node(2, blocked_by=[(1, "CLOSED")])]))
    assert not [line for line in lines if "n1" in line]


def test_a_blocker_in_another_milestone_is_a_dashed_node_with_its_status():
    nodes = [node(1, "explore", milestone="W2"), node(2, blocked_by=[(1, "OPEN")])]
    lines = mermaid(draw(nodes))
    assert '  n1["#1<br>issue 1<br>בתכנון"]' in lines
    assert "  n1 --> n2" in lines
    assert "  class n1 outside" in lines


def test_a_blocker_in_another_repo_is_a_dashed_node():
    blocked = node(2)
    blocked["blockedBy"]["nodes"] = [
        {"number": 7, "state": "OPEN", "repository": "acme/other"}
    ]
    lines = mermaid(draw([blocked]))
    assert f'  nacme_other_7["acme/other#7<br>{OTHER_REPO}"]' in lines
    assert "  nacme_other_7 --> n2" in lines
    assert "  class nacme_other_7 outside" in lines


def test_a_blocker_shared_by_two_issues_is_drawn_once():
    nodes = [
        node(1, milestone="W2"),
        node(2, blocked_by=[(1, "OPEN")]),
        node(3, blocked_by=[(1, "OPEN")]),
    ]
    lines = mermaid(draw(nodes))
    assert len([line for line in lines if line.startswith('  n1["')]) == 1


def test_the_title_is_short_and_quotes_do_not_break_the_label():
    issue = node(1)
    issue["title"] = 'כותרת "ארוכה" מאוד שלא נכנסת בשורה אחת בטלפון'
    line = mermaid(draw([issue]))[1]
    assert '"' not in line.split('["', 1)[1].rsplit('"]', 1)[0]
    assert "#quot;" in line and "…" in line


@pytest.mark.parametrize(
    "nodes, sprint, expected",
    [
        ([node(1)], None, NO_SPRINT),
        ([node(1, milestone="W2")], "W1", EMPTY),
    ],
)
def test_nothing_to_draw_says_so_in_one_line(nodes, sprint, expected):
    text = draw(nodes, sprint)
    assert "```" not in text and text.endswith(expected)


def test_issues_without_arrows_sit_in_pairs_under_each_other():
    lines = mermaid(draw([node(n) for n in (1, 2, 3, 4, 5)]))
    # 1 and 2 on top, 3 and 4 under them, 5 at the bottom: two wide, not five.
    assert [line for line in lines if "~~~" in line] == [
        "  n2 ~~~ n3",
        "  n2 ~~~ n4",
        "  n4 ~~~ n5",
    ]


def test_a_chain_is_stacked_from_its_last_issue():
    nodes = [node(1), node(2, blocked_by=[(1, "OPEN")]), node(3)]
    lines = mermaid(draw(nodes))
    assert "  n2 ~~~ n3" in lines


def test_a_cycle_of_blockers_still_draws():
    nodes = [node(1, blocked_by=[(2, "OPEN")]), node(2, blocked_by=[(1, "OPEN")])]
    lines = mermaid(draw(nodes + [node(3)]))
    assert "  n1 --> n2" in lines and "  n2 --> n1" in lines
    assert "  n2 ~~~ n3" in lines


def test_html_and_entities_in_a_title_stay_text():
    issue = node(1)
    issue["title"] = "<details> & #12; in docs/<repo>"
    label = mermaid(draw([issue]))[1]
    assert not set("<>&") & set(label.split("<br>")[1])
    assert "#lt;details#gt; #amp; #35;12;" in label


def test_a_branching_chain_stacks_under_its_deepest_issue():
    nodes = [
        node(1),
        node(2, blocked_by=[(1, "OPEN")]),
        node(3, blocked_by=[(2, "OPEN")]),
        node(4, blocked_by=[(1, "OPEN")]),
        node(5),
    ]
    assert "  n3 ~~~ n5" in mermaid(draw(nodes))


def test_a_local_blocker_that_was_not_read_has_no_status():
    lines = mermaid(draw([node(2, blocked_by=[(9, "OPEN")])]))
    assert '  n9["#9<br>בלי סטטוס"]' in lines
