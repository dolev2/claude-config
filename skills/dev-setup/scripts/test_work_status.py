"""work_status.py: the four tables of /status (S-1.41)."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("work_status", HERE / "work_status.py")
work_status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(work_status)
from test_sprint_state import node  # noqa: E402

REPO = "acme/widgets"
LABELS = [{"name": name} for name in work_status.REQUIRED_LABELS]


def section(text: str, heading: str) -> str:
    """The text of one section, from its heading to the next one."""
    start = text.index(f"### {heading}")
    end = text.find("\n### ", start + 1)
    return text[start : end if end != -1 else None]


@pytest.fixture(autouse=True)
def billing_off(monkeypatch):
    """The billing flag is off unless a test says otherwise; no git in these tests."""
    monkeypatch.setattr(work_status.billing_flag, "current", lambda: None)


SPEC_URL = "https://github.com/acme/widgets/blob/HEAD/docs/specs/widgets.md"


def done(number, day, body=None):
    return {
        "number": number,
        "title": f"merged {number}",
        "closed_at": f"{day}T9:00Z",
        "body": body,
    }


def with_spec(line):
    return {"body": f"### הקשר / קישורים\n{line}\n"}


def test_all_four_tables_with_their_rows():
    nodes = [
        node(1, status="ready-to-execute"),
        node(2, status="explore", blocked_by=[(1, "OPEN")]),
        node(3, status="ready-to-execute", labels=("task", "costs-money")),
        node(4, status="plan-questions"),
        node(5, status="explore", milestone="W2"),
    ]
    nodes[-1]["milestone"]["number"] = 2  # a later sprint
    text = work_status.render(REPO, nodes, [done(9, "2026-11-10")])

    link = "[#9](https://github.com/acme/widgets/issues/9)"
    assert f"| {link} | merged 9 | Done, 2026-11-10 |" in text
    sprint = section(text, "מה פתוח בספרינט")
    assert "(W1)" in sprint and "#5]" not in sprint
    assert all(f"[#{n}]" in sprint for n in (1, 2, 3, 4))
    held = section(text, "מה חסום")
    assert "| מחכה ל-#1 |" in held and "| עולה כסף, מחכה לאישור |" in held
    assert "[#4]" in section(text, "מה מחכה לדולב")
    assert "שאלות לדולב" in section(text, "מה מחכה לדולב")


def test_the_old_approval_label_shows_as_ready_to_code():
    # S-1.64 (#466): no issue waits for a plan approval any more.
    text = work_status.render(REPO, [node(1, status="waiting-approval")], [])
    assert "מוכן לקוד" in section(text, "מה פתוח בספרינט")
    assert "[#1]" not in section(text, "מה מחכה לדולב")
    assert "תוכנית לאישור" not in text


def test_sprint_table_follows_the_sprint_order():
    nodes = [
        node(1, status="explore"),
        node(2, status="explore", blocking=[1]),
        node(3, status="ready-to-execute", labels=("bug",)),
    ]
    sprint = section(work_status.render(REPO, nodes, []), "מה פתוח בספרינט")
    # The bug first, then fewest waiting first (S-1.3): 1 waits on 2.
    assert sprint.index("[#3]") < sprint.index("[#1]") < sprint.index("[#2]")


def test_empty_tables_say_so():
    text = work_status.render(REPO, [node(1, status="ready-to-execute")], [])
    for heading in ("מה מוזג לאחרונה", "מה חסום", "מה מחכה לדולב"):
        assert section(text, heading).rstrip().endswith(work_status.EMPTY)


def test_no_open_sprint_still_shows_the_other_tables():
    text = work_status.render(REPO, [], [done(9, "2026-11-10")])
    assert "אין ספרינט פתוח." in section(text, "מה פתוח בספרינט")
    assert "[#9]" in section(text, "מה מוזג לאחרונה")
    assert section(text, "מה מחכה לדולב").rstrip().endswith(work_status.EMPTY)


def test_blocked_issue_that_costs_money_gets_one_row():
    nodes = [
        node(1, status="ready-to-execute"),
        node(2, blocked_by=[(1, "OPEN")], labels=("task", "costs-money")),
    ]
    held = section(work_status.render(REPO, nodes, []), "מה חסום")
    assert held.count("[#2]") == 1 and "| מחכה ל-#1, ועולה כסף |" in held


def test_blocker_in_another_repo_is_named():
    entry = {"number": 2, "blocked_by": [1], "outside_blockers": ["acme/other#7"]}
    assert work_status.blocked_status(entry) == "מחכה ל-#1, acme/other#7"


@pytest.mark.parametrize(
    "title, expected",
    [
        ("short", "short"),
        ("x" * 50, "x" * 50),
        ("x" * 60, "x" * 49 + "…"),
        ("a | b", "a \\| b"),
    ],
)
def test_short_titles(title, expected):
    assert work_status.short(title) == expected


def test_repo_without_pipeline_prints_one_sentence(monkeypatch, capsys):
    monkeypatch.setattr(work_status, "api_list", lambda path: [{"name": "bug"}])
    work_status.main(["--repo", REPO])
    out = capsys.readouterr().out
    assert out.strip() == work_status.NO_PIPELINE.format(repo=REPO)


def test_github_not_answering_exits_1_without_tables(monkeypatch, capsys):
    def fail(path):
        sys.exit("gh api failed:\nHTTP 502")

    monkeypatch.setattr(work_status, "api_list", lambda path: LABELS)
    monkeypatch.setattr(work_status, "open_issue_nodes", lambda repo, with_body: [])
    monkeypatch.setattr(work_status, "recent_done", fail)
    with pytest.raises(SystemExit) as exit_info:
        work_status.main(["--repo", REPO])
    out = capsys.readouterr().out
    assert exit_info.value.code == 1
    assert "המשימות שמוזגו" in out and "HTTP 502" in out and "###" not in out
    assert REPO in out


@pytest.mark.parametrize(
    "repo, folder, source, expected",
    [
        (None, "acme/here", "acme/first", "acme/here"),
        (None, None, "acme/first", "acme/first"),
        ("acme/asked", "acme/here", "acme/first", "acme/asked"),
        (None, None, None, None),
        (None, None, "", None),
        (None, None, "https://github.com/acme/first.git", "acme/first"),
    ],
)
def test_choose_repo_folder_before_sources(repo, folder, source, expected):
    assert work_status.choose_repo(repo, folder, source) == expected


@pytest.mark.parametrize(
    "unread, reason",
    [(False, work_status.NO_SOURCES), (True, work_status.SOURCES_UNREAD)],
)
def test_no_repo_says_why(unread, reason, monkeypatch, capsys):
    monkeypatch.setattr(work_status, "repo_of_folder", lambda: None)
    argv = ["--sources-unread"] if unread else []
    with pytest.raises(SystemExit) as exit_info:
        work_status.main(argv)
    out = capsys.readouterr().out
    assert exit_info.value.code == 3
    assert out.strip() == work_status.no_repo(unread)
    assert "###" not in out


def test_folder_outside_a_repo_shows_the_first_source(monkeypatch, capsys):
    fake_github(monkeypatch, [node(1)])
    monkeypatch.setattr(work_status, "repo_of_folder", lambda: None)
    work_status.main(["--source-repo", REPO])
    assert capsys.readouterr().out.startswith(work_status.REPO_LINE.format(repo=REPO))


def test_a_source_without_the_pipeline_is_not_skipped(monkeypatch, capsys):
    monkeypatch.setattr(work_status, "repo_of_folder", lambda: None)
    monkeypatch.setattr(work_status, "api_list", lambda path: [{"name": "bug"}])
    work_status.main(["--source-repo", REPO])
    assert capsys.readouterr().out.strip() == work_status.NO_PIPELINE.format(repo=REPO)


def test_the_folder_repo_wins_over_the_sources(monkeypatch, capsys):
    monkeypatch.setattr(work_status, "repo_of_folder", lambda: "acme/here")
    work_status.main(["--which", "--source-repo", REPO])
    assert capsys.readouterr().out.strip() == "acme/here"


def test_which_runs_and_prints_only_the_repo(tmp_path):
    def which(*flags):
        return subprocess.run(
            [sys.executable, str(HERE / "work_status.py"), "--which", *flags],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            cwd=tmp_path,
        )

    found = which("--source-repo", REPO)
    assert (found.returncode, found.stdout) == (0, f"{REPO}\n")
    missing = which()
    assert missing.returncode == 3 and "אין ריפו לסקור" in missing.stdout


def test_the_repo_line_opens_the_output():
    text = work_status.render(REPO, [node(1)], [], sessions={})
    first, rest = text.split("\n\n", 1)
    assert first == "**הריפו:** [acme/widgets](https://github.com/acme/widgets)"
    assert rest.startswith("### ")


def test_script_runs_and_exits_0_on_help():
    run = subprocess.run(
        [sys.executable, str(HERE / "work_status.py"), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0 and "--repo" in run.stdout


@pytest.mark.parametrize(
    "line, expected",
    [
        ("אפיון: docs/specs/widgets.md S-1.2", f"[S-1.2]({SPEC_URL}#s-12--two)"),
        ("אפיון: docs/specs/widgets.md S-1.9", f"[S-1.9]({SPEC_URL})"),
        (
            "אפיון: docs/specs/widgets.md S-1.2, S-1.9",
            f"[S-1.2]({SPEC_URL}#s-12--two), [S-1.9]({SPEC_URL})",
        ),
        ("בלי שורת אפיון", work_status.NO_PART),
    ],
)
def test_spec_cell_links_to_the_part_heading(line, expected):
    anchors = {"docs/specs/widgets.md": {"S-1.2": "s-12--two"}}
    assert work_status.spec_cell(REPO, with_spec(line), anchors) == expected


def test_issue_without_body_gets_a_dash():
    assert work_status.spec_cell(REPO, {"body": None}, {}) == work_status.NO_PART


def test_every_table_has_the_spec_column():
    body = with_spec("אפיון: docs/specs/widgets.md S-1.2")["body"]
    text = work_status.render(REPO, [], [done(9, "2026-11-10", body)])
    assert work_status.HEADER in text
    assert f"| [S-1.2]({SPEC_URL}) |" in section(text, "מה מוזג לאחרונה")


def test_unreadable_spec_file_still_gives_the_tables(monkeypatch):
    def read(path, *flags):
        if "missing" in path:
            sys.exit("HTTP 404")
        return "## S-1.2 · Two\n"

    monkeypatch.setattr(work_status, "gh_api", read)
    issues = [
        with_spec("אפיון: docs/specs/widgets.md S-1.2"),
        with_spec("אפיון: docs/specs/missing.md S-2.1"),
        {"body": None},
    ]
    assert work_status.read_anchors(REPO, issues) == {
        "docs/specs/missing.md": {},
        "docs/specs/widgets.md": {"S-1.2": "s-12--two"},
    }


def test_the_graph_comes_after_the_tables():
    nodes = [node(1), node(2, status="explore", blocked_by=[(1, "OPEN")])]
    text = work_status.render(REPO, nodes, [])
    assert text.index("### מה מחכה לדולב") < text.index("### גרף החסימות")
    assert "  n1 --> n2" in section(text, "גרף החסימות")


def test_the_graph_without_a_sprint_says_so():
    text = work_status.render(REPO, [], [])
    assert section(text, "גרף החסימות").rstrip().endswith("אין ספרינט פתוח.")


def fake_github(monkeypatch, nodes):
    monkeypatch.setattr(work_status, "api_list", lambda path: LABELS)
    monkeypatch.setattr(work_status, "open_issue_nodes", lambda repo, with_body: nodes)
    monkeypatch.setattr(work_status, "recent_done", lambda repo: [])
    monkeypatch.setattr(work_status, "read_anchors", lambda repo, issues: {})


def test_page_flag_writes_the_page_with_the_active_mark(monkeypatch, capsys, tmp_path):
    fake_github(monkeypatch, [node(1)])
    sessions = tmp_path / "sessions.json"
    sessions.write_text(
        '[{"id": "s1", "title": "widgets: claude/issue-1-x", "tags": [], '
        '"session_status": "SESSION_STATUS_IDLE", "created_at": null}]'
    )
    target = tmp_path / "page.html"
    work_status.main(
        ["--repo", REPO, "--page", str(target), "--sessions", str(sessions)]
    )
    out = capsys.readouterr().out
    assert "מוכן לקוד · פעיל |" in out
    assert work_status.SESSIONS_NOT_READ not in out
    text = target.read_text(encoding="utf-8")
    assert "https://github.com/acme/widgets/issues/1" in text
    assert "https://claude.ai/code/s1" in text
    assert "מוכן לקוד · פעיל" in text


def test_without_the_sessions_file_main_says_they_were_not_read(monkeypatch, capsys):
    fake_github(monkeypatch, [node(1)])
    work_status.main(["--repo", REPO])
    out = capsys.readouterr().out
    assert out.index(work_status.SESSIONS_NOT_READ) < out.index("### ")
    assert "פעיל |" not in out


ACTIVE_SESSION = [{"url": "https://claude.ai/code/s", "title": "", "created_at": None}]


def sprint_order(text: str) -> list[int]:
    """The issue numbers of the sprint table, top down."""
    lines = section(text, "מה פתוח בספרינט").splitlines()
    return [int(line.split("[#")[1].split("]")[0]) for line in lines if "[#" in line]


def test_an_active_issue_comes_first_in_the_sprint_table_with_the_mark():
    nodes = [node(1), node(2), node(3)]
    text = work_status.render(REPO, nodes, [], sessions={3: ACTIVE_SESSION})
    assert sprint_order(text) == [3, 1, 2]
    sprint = section(text, "מה פתוח בספרינט")
    assert "| מוכן לקוד · פעיל |" in sprint
    assert sprint.count("פעיל") == 1
    assert work_status.SESSIONS_NOT_READ not in text


def test_several_active_issues_keep_the_sprint_order_between_them():
    nodes = [node(1), node(2), node(3), node(4)]
    sessions = {4: ACTIVE_SESSION, 2: ACTIVE_SESSION}
    text = work_status.render(REPO, nodes, [], sessions=sessions)
    assert sprint_order(text) == [2, 4, 1, 3]


def test_no_active_issue_keeps_the_order_and_has_no_mark():
    nodes = [node(1), node(2)]
    text = work_status.render(REPO, nodes, [], sessions={})
    assert sprint_order(text) == [1, 2]
    assert "פעיל" not in text
    assert work_status.SESSIONS_NOT_READ not in text


def test_sessions_not_read_say_so_under_the_repo_line_with_no_mark():
    text = work_status.render(REPO, [node(1)], [], sessions=None)
    lines = text.split("\n\n")
    assert lines[0].startswith("**הריפו:**")
    assert lines[1] == work_status.SESSIONS_NOT_READ
    assert "פעיל |" not in text


def test_the_mark_reaches_the_blocked_and_waiting_tables_without_a_column():
    nodes = [
        node(1),
        node(2, blocked_by=[(1, "OPEN")]),
        node(3, status="plan-questions"),
        node(4, status="plan-questions"),
    ]
    sessions = {2: ACTIVE_SESSION, 4: ACTIVE_SESSION}
    text = work_status.render(REPO, nodes, [], sessions=sessions)
    assert "| מחכה ל-#1 · פעיל |" in section(text, "מה חסום")
    waiting = section(text, "מה מחכה לדולב")
    assert waiting.index("[#4]") < waiting.index("[#3]")
    rows = [line for line in text.splitlines() if line.startswith("| [#")]
    assert all(line.count(" | ") == 3 for line in rows)


def test_the_merged_table_does_not_move():
    merged = [done(8, "2026-11-10"), done(9, "2026-11-09")]
    text = work_status.render(REPO, [], merged, sessions={9: ACTIVE_SESSION})
    table_text = section(text, "מה מוזג לאחרונה")
    assert table_text.index("[#8]") < table_text.index("[#9]")
    assert "פעיל" not in table_text


def test_no_page_without_the_pipeline(monkeypatch, tmp_path):
    monkeypatch.setattr(work_status, "api_list", lambda path: [{"name": "bug"}])
    target = tmp_path / "page.html"
    work_status.main(["--repo", REPO, "--page", str(target)])
    assert not target.exists()


@pytest.mark.parametrize(
    "content",
    ["not json", "[1, 2]", '{"1": []}', '[{"title": "t"}]'],
)
def test_a_broken_sessions_file_exits_2(content, capsys, tmp_path):
    sessions = tmp_path / "sessions.json"
    sessions.write_text(content)
    with pytest.raises(SystemExit) as exit_info:
        work_status.main(["--repo", REPO, "--sessions", str(sessions)])
    assert exit_info.value.code == 2
    assert "קובץ הסשנים" in capsys.readouterr().err


BILLING_ON = {
    "since": "2026-11-15T10:00:00",
    "source": "auto",
    "run": "https://x/1",
    "notice": "החיוב ב-GitHub חסום מאז 2026-11-15 (נדלק לבד בריצה https://x/1).",
}


@pytest.mark.parametrize(("billing", "shown"), [(BILLING_ON, True), (None, False)])
def test_the_billing_line_comes_before_the_tables(billing, shown):
    text = work_status.render(REPO, [node(1)], [], billing=billing)
    assert (BILLING_ON["notice"] in text) is shown
    if shown:
        assert text.index(BILLING_ON["notice"]) < text.index("### ")


def test_main_shows_the_billing_line_while_the_flag_is_on(monkeypatch, capsys):
    monkeypatch.setattr(work_status, "api_list", lambda path: LABELS)
    monkeypatch.setattr(work_status, "open_issue_nodes", lambda repo, with_body: [])
    monkeypatch.setattr(work_status, "recent_done", lambda repo: [])
    monkeypatch.setattr(work_status, "read_anchors", lambda repo, issues: {})
    monkeypatch.setattr(work_status.billing_flag, "current", lambda: BILLING_ON)
    work_status.main(["--repo", REPO])
    assert BILLING_ON["notice"] in capsys.readouterr().out
