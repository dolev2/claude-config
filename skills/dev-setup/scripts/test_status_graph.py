"""status_graph.py: the sprint's blocking graph for /status (S-1.48)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from status_graph import (  # noqa: E402
    CANCELLED_WORD,
    DONE_WORD,
    EMPTY,
    NO_SPRINT,
    OTHER_REPO,
    TITLE_LIMIT,
    graph,
    labels_text,
    layout,
    mermaid_lines,
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


LONG_TITLE = "כותרת ארוכה מאוד שלא נכנסת בשלושים התווים של הגרף בצ'אט"


def lines_with_limit(**limit: int | None) -> str:
    """The node line of one issue with LONG_TITLE, drawn with `title_limit` if given."""
    issue = node(1)
    issue["title"] = LONG_TITLE
    shape = layout([issue], [issue], status_he)
    return mermaid_lines(shape, **limit)[1]


def test_title_limit_none_keeps_the_whole_title():
    assert LONG_TITLE in lines_with_limit(title_limit=None)
    assert "…" not in lines_with_limit(title_limit=None)


def test_title_limit_cuts_where_asked_and_the_default_stays_the_chats():
    assert "…" in lines_with_limit(title_limit=40)
    assert lines_with_limit() == lines_with_limit(title_limit=TITLE_LIMIT)
    assert LONG_TITLE[: TITLE_LIMIT - 1].rstrip() + "…" in lines_with_limit()


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


# A closed sprint's graph (S-1.74): only on request, with every issue and arrow.


def closed(number, reason="COMPLETED", **kwargs) -> dict:
    """A sprint issue closed with `reason`."""
    return node(number, "done", **kwargs) | {"state": "CLOSED", "stateReason": reason}


def closed_lines(sprint_nodes: list[dict], nodes: list[dict] = ()) -> list[str]:
    """The Mermaid lines of a closed sprint's graph."""
    shape = layout(sprint_nodes, list(nodes), status_he, closed_sprint=True)
    return mermaid_lines(shape)


def test_a_done_blocker_shows_done_with_its_arrow():
    lines = closed_lines([closed(1), closed(2, blocked_by=[(1, "CLOSED")])])
    assert f'  n1["#1<br>issue 1<br>{DONE_WORD}<br>task"]' in lines
    assert f'  n2["#2<br>issue 2<br>{DONE_WORD}<br>task"]' in lines
    assert "  n1 --> n2" in lines


def test_a_cancelled_issue_shows_cancelled_with_its_arrows():
    sprint = [closed(1, "NOT_PLANNED"), closed(2, blocked_by=[(1, "CLOSED")])]
    lines = closed_lines(sprint)
    assert f'  n1["#1<br>issue 1<br>{CANCELLED_WORD}<br>task"]' in lines
    assert "  n1 --> n2" in lines


def test_a_sprint_with_no_blocking_has_no_arrow():
    lines = closed_lines([closed(1), closed(2)])
    assert not [line for line in lines if "-->" in line]


def test_a_reopened_issue_shows_its_usual_status():
    reopened = node(1, "explore") | {"state": "OPEN", "stateReason": "REOPENED"}
    lines = closed_lines([reopened, closed(2, blocked_by=[(1, "OPEN")])])
    assert '  n1["#1<br>issue 1<br>בתכנון<br>task"]' in lines
    assert "  n1 --> n2" in lines


def test_a_node_without_state_reads_as_open():
    lines = closed_lines([node(1, "explore")])
    assert '  n1["#1<br>issue 1<br>בתכנון<br>task"]' in lines


def test_closed_blockers_outside_the_sprint_are_dashed_and_marked():
    waiting = closed(3)
    waiting["blockedBy"]["nodes"] = [
        {"number": 1, "state": "CLOSED", "stateReason": "COMPLETED"},
        {
            "number": 7,
            "state": "CLOSED",
            "stateReason": "NOT_PLANNED",
            "repository": "acme/other",
        },
    ]
    lines = closed_lines([waiting])
    assert f'  n1["#1<br>{DONE_WORD}"]' in lines
    assert f'  nacme_other_7["acme/other#7<br>{CANCELLED_WORD}"]' in lines
    assert "  n1 --> n3" in lines and "  nacme_other_7 --> n3" in lines
    assert "  class n1,nacme_other_7 outside" in lines


def test_an_open_blocker_outside_the_sprint_keeps_its_status():
    other_milestone = node(1, "explore", milestone="W2")
    lines = closed_lines([closed(2, blocked_by=[(1, "OPEN")])], nodes=[other_milestone])
    assert '  n1["#1<br>issue 1<br>בתכנון<br>task"]' in lines


def test_without_the_request_the_graph_is_as_before():
    nodes = [
        node(1, milestone="W2") | {"state": "CLOSED"},
        node(2, blocked_by=[(1, "CLOSED")]),
    ]
    as_before = mermaid(draw(nodes))
    assert as_before == mermaid_lines(layout([nodes[1]], nodes, status_he))
    assert not [line for line in as_before if "n1" in line]
    assert not [line for line in as_before if DONE_WORD in line]


@pytest.mark.parametrize("reason", ["NOT_PLANNED", "DUPLICATE", "not_planned"])
def test_closed_without_being_built_is_cancelled(reason):
    lines = closed_lines([closed(1, reason)])
    assert f'  n1["#1<br>issue 1<br>{CANCELLED_WORD}<br>task"]' in lines


def test_rest_spelling_of_an_open_issue_reads_as_open():
    lines = closed_lines([node(1, "explore") | {"state": "open"}])
    assert '  n1["#1<br>issue 1<br>בתכנון<br>task"]' in lines


def test_an_open_blocker_in_another_repo_keeps_other_repo():
    waiting = closed(2)
    waiting["blockedBy"]["nodes"] = [
        {"number": 7, "state": "OPEN", "repository": "acme/other"}
    ]
    lines = closed_lines([waiting])
    assert f'  nacme_other_7["acme/other#7<br>{OTHER_REPO}"]' in lines
