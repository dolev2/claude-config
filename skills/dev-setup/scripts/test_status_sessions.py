"""status_sessions.py: which session belongs to which issue (S-1.57)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from status_sessions import ARCHIVED, by_issue, issue_of, read_sessions  # noqa: E402

REPO = "acme/widgets"


def row(title="", tags=(), status="SESSION_STATUS_IDLE", sid="s1", created=None):
    return {
        "id": sid,
        "title": title,
        "tags": list(tags),
        "session_status": status,
        "created_at": created,
    }


@pytest.mark.parametrize(
    ("session", "expected"),
    [
        (row(tags=["repo:acme/widgets", "issue:7"]), 7),
        (row(tags=["repo:Acme/Widgets", "issue:7"]), 7),
        (row("widgets: claude/issue-7-fix-it"), 7),
        (row("widgets: claude/issue-7-fix-it", tags=["repo:acme/widgets"]), 7),
        (row(tags=["repo:acme/widgets", "issue:7"], status=ARCHIVED), None),
        (row("widgets: claude/issue-7-fix-it", status=ARCHIVED), None),
        (row("widgets: claude/issue-7-x", tags=["repo:other/widgets"]), None),
        (row("other: claude/issue-5-x"), None),
        (row("widgets: claude/issue-50-x"), 50),
        (row("widgets: claude/issue-x"), None),
        (row("widgets: some work"), None),
        ({"id": "s1"}, None),
    ],
)
def test_the_issue_of_a_session(session, expected):
    assert issue_of(session, REPO) == expected


def test_issue_50_is_not_issue_5():
    sessions = by_issue([row("widgets: claude/issue-50-x")], REPO)
    assert 5 not in sessions and 50 in sessions


def test_by_issue_keeps_every_session_of_an_issue():
    rows = [
        row("widgets: claude/issue-3-a", sid="a", created="2026-11-01"),
        row(tags=["repo:acme/widgets", "issue:3"], sid="b"),
        row("widgets: nothing", sid="c"),
    ]
    sessions = by_issue(rows, REPO)
    assert list(sessions) == [3]
    assert sessions[3][0] == {
        "url": "https://claude.ai/code/a",
        "title": "widgets: claude/issue-3-a",
        "created_at": "2026-11-01",
    }
    assert sessions[3][1]["url"] == "https://claude.ai/code/b"


def test_read_sessions_reads_the_raw_rows(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text(json.dumps([row("widgets: claude/issue-4-x")]), encoding="utf-8")
    assert list(read_sessions(str(path), REPO)) == [4]


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"1": []}',
        "[5]",
        '[{"title": "no id"}]',
        '[{"id": "s", "title": 5}]',
        '[{"id": "s", "tags": "repo:acme/widgets"}]',
    ],
)
def test_a_broken_file_exits_2(content, tmp_path, capsys):
    path = tmp_path / "sessions.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        read_sessions(str(path), REPO)
    assert exit_info.value.code == 2
    assert "קובץ הסשנים" in capsys.readouterr().err


def test_a_missing_file_exits_2(tmp_path):
    with pytest.raises(SystemExit) as exit_info:
        read_sessions(str(tmp_path / "none.json"), REPO)
    assert exit_info.value.code == 2
