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
        node(4, status="waiting-approval"),
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
    assert "תוכנית לאישור" in section(text, "מה מחכה לדולב")


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
