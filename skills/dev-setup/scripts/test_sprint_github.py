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


def test_a_pushed_branch_gives_the_files_it_changed(monkeypatch):
    fake_api(
        monkeypatch,
        {
            "repos/o/r/git/matching-refs/heads/claude/issue-7-x": [
                {"ref": "refs/heads/claude/issue-7-x"}
            ],
            "repos/o/r/compare/main...claude/issue-7-x": {
                "files": [{"filename": "a.py"}, {"filename": "b/c.md"}]
            },
        },
    )
    assert sprint_github.branch_files("o/r", "main", "claude/issue-7-x") == {
        "a.py",
        "b/c.md",
    }


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
