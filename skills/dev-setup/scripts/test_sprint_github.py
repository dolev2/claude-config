"""sprint_github.py: the branch and PR files sprint_state.py reads from GitHub."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sprint_github  # noqa: E402


def fake_api(monkeypatch, answers):
    calls = []

    def api(path):
        calls.append(path)
        return answers[path]

    monkeypatch.setattr(sprint_github, "api", api)
    return calls


REF = "repos/o/r/git/matching-refs/heads/claude/issue-7-x"
COMPARE = "repos/o/r/compare/main...claude/issue-7-x"


def fake_compare(monkeypatch, code, out, err=""):
    calls = []

    def run_command(*args):
        calls.append(args)
        return code, out, err

    monkeypatch.setattr(sprint_github, "run_command", run_command)
    return calls


def test_a_pushed_branch_gives_the_files_it_changed(monkeypatch):
    fake_api(monkeypatch, {REF: [{"ref": "refs/heads/claude/issue-7-x"}]})
    out = '{"files": [{"filename": "a.py"}, {"filename": "b/c.md"}]}'
    calls = fake_compare(monkeypatch, 0, out)
    assert sprint_github.branch_files("o/r", "main", "claude/issue-7-x") == {
        "a.py",
        "b/c.md",
    }
    assert calls == [("gh", "api", COMPARE)]


def test_a_compare_that_answers_404_is_no_files(monkeypatch):
    # The branch was deleted between the two calls, or shares no history with main.
    fake_api(monkeypatch, {REF: [{"ref": "refs/heads/claude/issue-7-x"}]})
    fake_compare(monkeypatch, 1, "", "gh: Not Found (HTTP 404)")
    assert sprint_github.branch_files("o/r", "main", "claude/issue-7-x") == set()


def test_a_missing_branch_is_no_files_and_no_compare(monkeypatch):
    # matching-refs matches by prefix: issue-7-x-old is not issue-7-x.
    calls = fake_api(
        monkeypatch,
        {
            "repos/o/r/git/matching-refs/heads/claude/issue-7-x": [
                {"ref": "refs/heads/claude/issue-7-x-old"}
            ]
        },
    )
    assert sprint_github.branch_files("o/r", "main", "claude/issue-7-x") == set()
    assert len(calls) == 1


def test_pr_files(monkeypatch):
    monkeypatch.setattr(
        sprint_github,
        "api_list",
        lambda path: (
            [{"filename": "a.py"}] if path == "repos/o/r/pulls/40/files" else []
        ),
    )
    assert sprint_github.pr_files("o/r", 40) == {"a.py"}
