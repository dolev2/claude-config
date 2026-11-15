"""status_graph.py: the sprint's blocking graph for /status (S-1.48)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from status_graph import (  # noqa: E402
    EMPTY,
    NO_SPRINT,
    OTHER_REPO,
    TITLE_LIMIT,
    graph,
    labels_text,
)
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
    lines = mermaid(draw([node(1, "explore", labels=()), node(2, labels=())]))
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
    nodes = [
        node(1, "explore", labels=("bug", "area:scripts"), milestone="W2"),
        node(2, blocked_by=[(1, "OPEN")]),
    ]
    lines = mermaid(draw(nodes))
    assert '  n1["#1<br>issue 1<br>בתכנון<br>bug · area:scripts"]' in lines
    assert "  n1 --> n2" in lines
    assert "  class n1 outside" in lines


def test_a_blocker_in_another_repo_is_a_dashed_node():
    blocked = node(2)
    blocked["blockedBy"]["nodes"] = [
        {"number": 7, "state": "OPEN", "repository": "acme/other"}
    ]
    lines = mermaid(draw([blocked]))
    # Another repo is not read: no status and no labels line.
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


def test_the_labels_go_under_the_status_without_the_status_label():
    lines = mermaid(draw([node(1, labels=("task", "area:skills", "process"))]))
    assert '  n1["#1<br>issue 1<br>מוכן לקוד<br>task · area:skills · process"]' in lines
    assert "status:" not in lines[1]


def test_many_labels_wrap_and_none_is_cut():
    names = ("task", "area:skills", "area:scripts", "process", "costs-money")
    rows = labels_text(names).split("<br>")
    assert rows == ["task · area:skills", "area:scripts · process", "costs-money"]
    assert all(len(row) <= TITLE_LIMIT for row in rows)
    assert "…" not in "".join(rows)


def test_one_long_label_stays_whole_on_its_own_line():
    long = "a-label-that-is-much-longer-than-the-limit"
    assert labels_text(["task", long]).split("<br>") == ["task", long]


def test_a_label_with_codes_is_written_safe():
    assert labels_text(['p#1 "x"']) == "p#35;1 #quot;x#quot;"


def active_draw(nodes: list[dict], active: set[int]) -> list[str]:
    in_sprint = [n for n in nodes if n["milestone"]["title"] == "W1"]
    return mermaid(graph(in_sprint, nodes, status_he, active))


def declared(lines: list[str]) -> list[str]:
    """The node ids in the order they are declared."""
    return [line.split("[")[0].strip() for line in lines if '["' in line]


def test_an_active_node_is_declared_first_and_marked():
    lines = active_draw([node(1, labels=()), node(2, labels=())], {2})
    assert declared(lines)[:2] == ["n2", "n1"]
    assert '  n2["#2<br>issue 2<br>מוכן לקוד · פעיל"]' in lines
    assert '  n1["#1<br>issue 1<br>מוכן לקוד"]' in lines


def test_an_active_node_keeps_the_arrow_from_its_blocker():
    nodes = [node(1), node(2, blocked_by=[(1, "OPEN")])]
    assert "  n1 --> n2" in active_draw(nodes, {2})


def test_an_active_blocker_outside_the_sprint_is_marked_and_stays():
    nodes = [node(1, milestone="W2", labels=()), node(2, blocked_by=[(1, "OPEN")])]
    lines = active_draw(nodes, {1})
    assert declared(lines) == ["n2", "n1"]
    assert any(line.startswith("  n1[") and "· פעיל" in line for line in lines)


def test_no_active_set_keeps_the_graph_as_it_was():
    nodes = [node(1), node(2)]
    assert active_draw(nodes, set()) == mermaid(draw(nodes))
