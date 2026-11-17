"""handover_prompt.py: the opening prompt of a new orchestrator (S-2.12)."""

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import handover_prompt  # noqa: E402
import sprint_github  # noqa: E402

LINE = "since 2026-11-15T09:00:00Z expect 12=explore pipeline_sha a1 session_sha b2"
SHA = "c0ffee1234567890"
FULL_STATE = {
    "sprint": "Sprint 4",
    "waiting_dolev": [{"number": 20, "title": "plan me", "status": "plan-questions"}],
    "merge_queue": [
        {"number": 15, "pr": 40, "ci": "success", "mergeable_state": "clean"}
    ],
    "proposals": [
        {"number": 30, "title": "idea", "stage": "review"},
        {"number": 31, "title": "writing", "stage": "writing"},
    ],
}
ISSUES = {
    12: {"number": 12, "title": "plan it", "status": "status:explore"},
    15: {"number": 15, "title": "code it", "status": "status:in-review"},
}


def write_state(tmp_path: Path, state: dict) -> Path:
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def args_for(tmp_path, state=FULL_STATE, *extra):
    argv = [
        "--status-line", LINE,
        "--state", str(write_state(tmp_path, state)),
        "--session", "session_old",
        "--started", "2026-11-15T08:00:00Z",
        *extra,
    ]  # fmt: skip
    return handover_prompt.parse(argv)


def test_a_full_state_gives_every_section_in_order(tmp_path):
    notes = tmp_path / "notes.md"
    notes.write_text("דולב: לא למזג את #15 לפני יום ראשון.\n", encoding="utf-8")
    args = args_for(
        tmp_path,
        FULL_STATE,
        "--children", "session_a=12,session_b=15",
        "--moved", SHA,
        "--notes", str(notes),
    )  # fmt: skip
    merged = [{"number": 9, "title": "done one"}]

    text = handover_prompt.prompt(args, args.state_data, ISSUES.__getitem__, merged)

    lines = text.splitlines()
    assert "1. PR #40 של #15" in text
    assert lines[0] == "תריץ את הספרינט"
    assert f"~~~text\n{LINE}\n~~~" in text
    assert "```" not in text
    assert f"/commit/{SHA}" in text
    assert "`session_old`" in text
    assert "`session_a`: #12 plan it (`status:explore`), תכנון." in text
    assert "`session_b`: #15 code it (`status:in-review`), מחכה לדולב, PR #40." in text
    assert "1. PR #40 של #15" in text
    assert "1. #9 done one" in text
    assert "#20 plan me (`status:plan-questions`)" in text
    assert "למיזוג: PR #40 של #15, CI success" in text
    assert "הצעה #30 idea: PR של אפיון לסקירה" in text
    assert "#31" not in text
    assert text.rstrip().endswith("דולב: לא למזג את #15 לפני יום ראשון.")
    headings = [line for line in lines if line.startswith("#")]
    assert headings == [
        "## מסירה ממתזמר קודם",
        "### שורת המצב של הבדיקה האחרונה",
        "### הבנים שרצים",
        "### ה-PRים שהמתזמר הקודם עקב אחריהם",
        "### מה מוזג בסשן",
        "### מה מחכה לדולב",
        "### מה דולב אמר בשיחה ולא נכתב ב-GitHub",
    ]


def test_an_empty_state_says_none_in_every_section(tmp_path):
    args = args_for(tmp_path, {"sprint": "Sprint 4"}, "--moved", SHA)

    text = handover_prompt.prompt(args, args.state_data, ISSUES.__getitem__, [])

    assert text.count("\nאין.\n") == 5
    assert text.endswith("\nאין.\n")


def test_a_repair_childs_open_pr_is_shown_and_followed(tmp_path):
    issues = {12: {"number": 12, "title": "fix it", "status": "status:needs-repair"}}
    args = args_for(tmp_path, FULL_STATE, "--children", "s_a=12", "--moved", SHA)

    text = handover_prompt.prompt(
        args, args.state_data, issues.__getitem__, [], {12: 55}
    )

    assert "`s_a`: #12 fix it (`status:needs-repair`), תיקון, PR #55." in text
    assert "1. PR #55 של #12\n2. PR #40 של #15" in text


def test_a_started_that_is_not_iso_exits(tmp_path, capsys):
    argv = ["--status-line", LINE, "--state", str(write_state(tmp_path, {}))]
    argv += ["--session", "s", "--started", "yesterday", "--moved", SHA]

    with pytest.raises(SystemExit) as stop:
        handover_prompt.parse(argv)

    assert stop.value.code == 2
    assert "--started" in capsys.readouterr().err


def test_open_prs_of_maps_each_issue_to_the_pr_that_closes_it(monkeypatch):
    pulls = [
        {"number": 55, "body": "Closes #12", "head": {"sha": "a"}},
        {"number": 56, "body": "Refs #13", "head": {"sha": "b"}},
    ]
    monkeypatch.setattr(sprint_github, "api_list", lambda path: pulls)

    assert sprint_github.open_prs_of("o/r", [12, 13]) == {12: 55}
    assert sprint_github.open_prs_of("o/r", []) == {}


def test_a_failed_refresh_gives_its_reason_instead_of_a_commit(tmp_path):
    args = args_for(tmp_path, FULL_STATE, "--reason", "git pull failed")

    text = handover_prompt.prompt(args, args.state_data, ISSUES.__getitem__, [])

    assert "הרענון של `~/.claude` נכשל: git pull failed" in text
    assert "/commit/" not in text


@pytest.mark.parametrize("children", ["session_a", "session_a=x", "=12"])
def test_children_without_a_session_and_an_issue_exit(tmp_path, children, capsys):
    with pytest.raises(SystemExit) as stop:
        args_for(tmp_path, FULL_STATE, "--moved", SHA, "--children", children)

    assert stop.value.code != 0
    assert "<session_id>=<issue number>" in capsys.readouterr().err


@pytest.mark.parametrize("content", ["not json", "[1, 2]"])
def test_a_state_that_is_not_a_json_object_exits(tmp_path, content, capsys):
    path = tmp_path / "state.json"
    path.write_text(content, encoding="utf-8")
    argv = ["--status-line", LINE, "--state", str(path), "--session", "s"]
    argv += ["--started", "2026-11-15T08:00:00Z", "--moved", SHA]

    with pytest.raises(SystemExit) as stop:
        handover_prompt.parse(argv)

    assert stop.value.code != 0
    assert "--state" in capsys.readouterr().err


@pytest.mark.parametrize(
    "drop", ["--status-line", "--moved"], ids=["no-status-line", "no-why"]
)
def test_a_missing_required_argument_exits(tmp_path, drop, capsys):
    argv = {
        "--status-line": LINE,
        "--state": str(write_state(tmp_path, FULL_STATE)),
        "--session": "s",
        "--started": "2026-11-15T08:00:00Z",
        "--moved": SHA,
    }
    argv.pop(drop)

    with pytest.raises(SystemExit) as stop:
        handover_prompt.parse([part for pair in argv.items() for part in pair])

    assert stop.value.code != 0
    assert capsys.readouterr().err


def closed(number, closed_at, sprint="Sprint 4", **extra):
    return {
        "number": number,
        "title": f"issue {number}",
        "closed_at": closed_at,
        "milestone": {"title": sprint} if sprint else None,
        **extra,
    }


def test_done_since_keeps_the_sprint_issues_closed_after_the_start(monkeypatch):
    answers = [
        closed(1, "2026-11-15T09:00:00Z"),
        closed(2, "2026-11-15T07:59:59Z"),
        closed(3, "2026-11-15T10:00:00Z", sprint="Sprint 3"),
        closed(4, "2026-11-15T10:00:00Z", pull_request={}),
        closed(5, "2026-11-15T08:30:00Z"),
    ]
    paths = []
    monkeypatch.setattr(
        sprint_github, "api_list", lambda path: paths.append(path) or answers
    )

    found = sprint_github.done_since("o/r", "Sprint 4", "2026-11-15T08:00:00.5+00:00")

    assert [i["number"] for i in found] == [5, 1]
    assert "labels=status:done" in paths[0] and "since=" in paths[0]


def test_issue_summary_reads_the_status_label(monkeypatch):
    issue = {"title": "t", "labels": [{"name": "task"}, {"name": "status:explore"}]}
    monkeypatch.setattr(sprint_github, "api", lambda path: issue)

    assert sprint_github.issue_summary("o/r", 7) == {
        "number": 7,
        "title": "t",
        "status": "status:explore",
    }


def test_main_prints_the_prompt(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(handover_prompt, "done_since", lambda *_: [])
    monkeypatch.setattr(handover_prompt, "issue_summary", lambda _, n: ISSUES[n])
    monkeypatch.setattr(handover_prompt, "open_prs_of", lambda *_: {})
    argv = [
        "--status-line", LINE,
        "--state", str(write_state(tmp_path, FULL_STATE)),
        "--children", "session_a=12",
        "--session", "session_old",
        "--started", "2026-11-15T08:00:00Z",
        "--moved", SHA,
        "--repo", "o/r",
    ]  # fmt: skip

    handover_prompt.main(argv)

    out = capsys.readouterr().out
    assert out.startswith("תריץ את הספרינט\n")
    assert "#12 plan it" in out
