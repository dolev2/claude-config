"""status_page.py: the clickable blocking graph of /status (S-1.50)."""

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from status_graph import EMPTY, NO_SPRINT, layout  # noqa: E402
from status_page import (  # noqa: E402
    FONT,
    HOW_TO_REFRESH,
    SESSIONS_NOT_READ,
    link_lines,
    page,
    page_title,
    session_order,
)
from test_sprint_state import node  # noqa: E402
from test_status_graph import status_he  # noqa: E402

REPO = "o/r"


def build(nodes: list[dict], sessions: dict | None = None, sprint: str = "W1") -> str:
    in_sprint = [n for n in nodes if n["milestone"]["title"] == sprint]
    return page(REPO, layout(in_sprint, nodes, status_he), nodes, sessions, "now")


def node_line(text: str, number: int) -> str:
    """The Mermaid line of node `number` on the page (escaped inside <pre>)."""
    return next(line for line in text.splitlines() if line.startswith(f"  n{number}["))


def session(url: str, created: str) -> dict:
    return {"url": url, "title": "t", "created_at": created}


def test_the_title_is_fixed_by_the_repo_name():
    assert page_title("dolev2/claude-config") == "גרף החסימות · claude-config"
    assert "<title>גרף החסימות · r</title>" in build([node(1)])


def test_every_node_links_to_its_issue():
    line = node_line(build([node(1)]), 1)
    assert "href=&#x27;https://github.com/o/r/issues/1&#x27;" in line
    assert "/pull/" not in line


def test_the_labels_come_before_the_links():
    line = node_line(build([node(1, labels=("bug", "area:skills"))]), 1)
    assert "bug · area:skills" in line
    assert line.index("bug · area:skills") < line.index("href=")


def test_an_open_pr_gets_a_link():
    line = node_line(build([node(1, prs=[7])]), 1)
    assert "https://github.com/o/r/pull/7" in line
    assert "PR 7" in line


def test_each_session_gets_a_link():
    sessions = {1: [session("https://claude.ai/code/s1", "2026-11-01T00:00:00Z")]}
    line = node_line(build([node(1)], sessions), 1)
    assert "https://claude.ai/code/s1" in line
    assert "סשן" in line


def test_sessions_newest_first():
    entries = [
        session("old", "2026-11-01T00:00:00Z"),
        session("new", "2026-11-03T00:00:00Z"),
        session("mid", "2026-11-02T00:00:00Z"),
    ]
    assert [e["url"] for e in session_order(entries)] == ["new", "mid", "old"]
    assert entries[0]["url"] == "old"


def test_a_session_without_a_date_comes_last():
    entries = [{"url": "undated"}, session("dated", "2026-11-01T00:00:00Z")]
    assert [e["url"] for e in session_order(entries)] == ["dated", "undated"]


def test_sessions_not_read_says_so():
    text = build([node(1)], None)
    assert SESSIONS_NOT_READ in text
    assert SESSIONS_NOT_READ not in build([node(1)], {})


def test_every_page_says_how_to_refresh_right_after_the_time_line():
    pages = [
        build([node(1)], {}),
        page(REPO, None, [], {}, "now"),
        page(REPO, layout([], [], status_he), [], None, "now"),
    ]
    for text in pages:
        assert text.count(HOW_TO_REFRESH) == 1
        assert text.index("id='updated'") < text.index(HOW_TO_REFRESH)
    assert pages[2].index(HOW_TO_REFRESH) < pages[2].index(SESSIONS_NOT_READ)


def test_the_refresh_command_keeps_its_slash_in_a_right_to_left_line():
    assert "<code dir='ltr'>/status</code>" in HOW_TO_REFRESH


def test_a_blocker_outside_the_sprint_keeps_its_link():
    blocked = node(2, blocked_by=[(3, "OPEN")])
    outside = node(3, milestone="W2")
    text = build([blocked, outside])
    assert "https://github.com/o/r/issues/3" in node_line(text, 3)
    assert 'const EDGES = [["#3", "#2"]];' in text


def test_no_sprint_and_empty_sprint_show_the_chat_line():
    assert NO_SPRINT in page(REPO, None, [], {}, "now")
    empty = page(REPO, layout([], [], status_he), [], {}, "now")
    assert f"<p class='empty'>{EMPTY}</p>" in empty
    assert "class='graph'" not in empty


def test_a_url_cannot_close_the_label():
    sessions = {1: [session("https://x/'\"<b>#y", "2026-11-01T00:00:00Z")]}
    line = node_line(build([node(1)], sessions), 1)
    assert "<b>" not in line
    assert "'\"" not in line
    assert "%23y" in line
    assert "&amp;%23" not in line and "&%23" not in line


def test_the_page_is_rtl_with_both_themes():
    text = build([node(1)])
    assert '<div lang="he" dir="rtl">' in text
    assert "prefers-color-scheme: dark" in text
    assert ':root[data-theme="dark"]' in text


def test_the_active_mark_reaches_the_page():
    nodes = [node(1), node(2)]
    shape = layout(nodes, nodes, status_he, {2})
    sessions = {2: [session("https://claude.ai/code/s2", "2026-11-01T00:00:00Z")]}
    text = page(REPO, shape, nodes, sessions, "now")
    assert "· פעיל" in node_line(text, 2)
    assert "פעיל" not in node_line(text, 1)


def test_mermaid_measures_the_labels_in_the_page_font():
    """A label measured in one font and shown in another is cut at the edge (#427)."""
    text = build([node(1)])
    assert f"font-family: {FONT};" in text
    assert f"fontFamily: {json.dumps(FONT)}" in text
    assert f"themeVariables: {{ fontFamily: {json.dumps(FONT)} }}" in text


def test_the_graph_is_drawn_after_the_fonts_load():
    """A font that arrives after the measurement widens text the box no longer fits."""
    text = build([node(1)])
    assert "document.fonts.ready" in text
    assert text.index("document.fonts.ready") < text.index("mermaid.run(")


def test_a_label_that_still_overflows_stays_visible():
    assert ".graph foreignObject { overflow: visible; }" in build([node(1)])


def shown_lines(text: str) -> list[str]:
    """The link lines as the reader sees them: tags dropped, one string per line."""
    return [html.unescape(re.sub("<[^>]+>", "", part)) for part in text.split("<br>")]


def busy_node_links() -> str:
    """The links of a node with three PRs and three sessions, as on the page."""
    sessions = {
        1: [
            session(f"https://claude.ai/code/s{i}", f"2026-11-0{i}T00:00:00Z")
            for i in (1, 2, 3)
        ]
    }
    line = html.unescape(node_line(build([node(1, prs=[437, 438, 439])], sessions), 1))
    return line[
        line.index("<span class='lnks'>") : line.rindex("</span>") + len("</span>")
    ]


def test_a_single_link_is_one_line_with_no_dot():
    text = link_lines([("https://x/1", "משימה")])
    assert "<br>" not in text
    assert shown_lines(text) == ["משימה"]


def test_links_that_fit_share_one_line_with_dots():
    text = link_lines([("u1", "משימה"), ("u2", "PR 7"), ("u3", "סשן")])
    assert shown_lines(text) == ["משימה · PR 7 · סשן"]


def test_a_busy_node_breaks_between_links_only():
    lines = shown_lines(busy_node_links())
    assert len(lines) > 1
    for line in lines:
        assert not line.startswith("·") and not line.endswith("·")
        assert not line.startswith(" ") and not line.endswith(" ")


def test_every_link_is_whole_on_one_line_inside_a_lnks_span():
    text = busy_node_links()
    parts = text.split("<br>")
    for part in parts:
        assert part.startswith("<span class='lnks'>") and part.endswith("</span>")
    words = [w for part in shown_lines(text) for w in part.split(" · ")]
    assert words == ["משימה", "PR 437", "PR 438", "PR 439", "סשן", "סשן 2", "סשן 3"]


def test_links_and_their_lines_do_not_wrap_again():
    text = build([node(1)])
    assert re.search(r"\.lnk \{[^}]*white-space: nowrap;", text)
    assert ".lnks { white-space: nowrap; }" in text
