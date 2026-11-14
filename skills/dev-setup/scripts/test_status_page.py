"""status_page.py: the clickable blocking graph of /status (S-1.50)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from status_graph import EMPTY, NO_SPRINT, layout  # noqa: E402
from status_page import (  # noqa: E402
    SESSIONS_NOT_READ,
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
    assert "class='mermaid'" not in empty


def test_a_url_cannot_close_the_label():
    sessions = {1: [session("https://x/'\"<b>#y", "2026-11-01T00:00:00Z")]}
    line = node_line(build([node(1)], sessions), 1)
    assert "<b>" not in line
    assert "'\"" not in line
    assert "%23y" in line


def test_the_page_is_rtl_with_both_themes():
    text = build([node(1)])
    assert '<html lang="he" dir="rtl">' in text
    assert "prefers-color-scheme: dark" in text
    assert ':root[data-theme="dark"]' in text
