"""block_merge_subject.py: a merge with a hand-written subject is blocked."""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "block_merge_subject.py"
spec = importlib.util.spec_from_file_location("block_merge_subject", SCRIPT)
block_merge_subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(block_merge_subject)


class FakeStream:
    """A stdin or stderr stand-in with the `.buffer` the hook reads and writes."""

    def __init__(self, data: bytes = b"") -> None:
        self.buffer = io.BytesIO(data)

    def flush(self) -> None:
        pass


def run_hook(monkeypatch, raw: str) -> tuple[int, str]:
    """Run main() on raw stdin text; return the exit code and what went to stderr."""
    stderr = FakeStream()
    monkeypatch.setattr(sys, "stdin", FakeStream(raw.encode("utf-8")))
    monkeypatch.setattr(sys, "stderr", stderr)
    code = block_merge_subject.main()
    return code, stderr.buffer.getvalue().decode("utf-8")


def tool_call(command: str, tool: str = "Bash") -> str:
    return json.dumps({"tool_name": tool, "tool_input": {"command": command}})


@pytest.mark.parametrize(
    "command",
    [
        'gh pr merge 116 --squash --subject "15ב. Something (#116)"',
        'gh pr merge 116 --squash --subject="Something"',
        'gh pr merge 116 --squash -t "Something"',
        'gh pr merge 116 -st "Something"',
        "gh pr merge 116 -tSomething --squash",
        'gh pr merge --subject "x" 116',
        'gh pr merge 116 -b "body" -t "x"',
        'cd repo && gh pr merge 116 --squash --subject "x"',
        'GH_REPO=a/b gh pr merge 116 --squash -t "x"',
        '/usr/bin/gh pr merge 116 --subject "x"',
        'gh.exe pr merge 116 --subject "x"',
    ],
)
def test_merge_subject_is_blocked(monkeypatch, command):
    code, reason = run_hook(monkeypatch, tool_call(command))
    assert code == 2
    assert "gh pr edit" in reason


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge 116 --squash",
        "gh pr merge 116 --squash --delete-branch",
        "gh pr merge 116 -sd",
        'gh pr merge 116 --squash --body "-t is not a flag here"',
        'gh pr merge 116 --squash -b "--subject"',
        "gh pr merge 116 --squash -R dolev2/test-repo",
        'gh pr edit 116 --title "15ב. Something"',
        'gh pr create --title "x" -t "y"',
        'gh issue edit 113 --title "x"',
        'git merge --subject "x"',
        'echo gh pr merge 116 --subject "x"',
        "cat > notes.md <<'EOF'\ngh pr merge 116 --subject x\nEOF",
    ],
)
def test_other_commands_pass(monkeypatch, command):
    assert run_hook(monkeypatch, tool_call(command)) == (0, "")


def test_powershell_command_is_checked(monkeypatch):
    raw = tool_call('gh pr merge 116 --squash -t "x"; echo done', "PowerShell")
    code, _ = run_hook(monkeypatch, raw)
    assert code == 2


def test_other_tools_pass(monkeypatch):
    raw = json.dumps(
        {"tool_name": "Edit", "tool_input": {"command": "gh pr merge 1 --subject x"}}
    )
    assert run_hook(monkeypatch, raw) == (0, "")


@pytest.mark.parametrize("raw", ["", "not json", "[]", '{"tool_name": "Bash"}'])
def test_unreadable_input_passes(monkeypatch, raw):
    assert run_hook(monkeypatch, raw) == (0, "")


def mcp_call(tool: str, **tool_input) -> str:
    return json.dumps({"tool_name": tool, "tool_input": tool_input})


@pytest.mark.parametrize(
    "tool",
    [
        "mcp__github__merge_pull_request",
        "mcp__claude_ai_GitHub__merge_pull_request",
    ],
)
def test_mcp_merge_title_is_blocked(monkeypatch, tool):
    raw = mcp_call(tool, pullNumber=5, merge_method="squash", commit_title="15ב. x")
    code, reason = run_hook(monkeypatch, raw)
    assert code == 2
    assert "commit_title" in reason


@pytest.mark.parametrize(
    "tool_input",
    [
        {"pullNumber": 5, "merge_method": "squash"},
        {"pullNumber": 5, "commit_title": ""},
        {"pullNumber": 5, "commit_message": "body"},
    ],
)
def test_mcp_merge_without_title_passes(monkeypatch, tool_input):
    raw = mcp_call("mcp__github__merge_pull_request", **tool_input)
    assert run_hook(monkeypatch, raw) == (0, "")


def test_mcp_merge_with_odd_input_passes(monkeypatch):
    raw = json.dumps({"tool_name": "mcp__github__merge_pull_request", "tool_input": []})
    assert run_hook(monkeypatch, raw) == (0, "")


def test_other_mcp_tool_with_title_passes(monkeypatch):
    raw = mcp_call("mcp__github__update_pull_request", commit_title="x")
    assert run_hook(monkeypatch, raw) == (0, "")


@pytest.mark.parametrize(
    "command",
    [
        "gh api -X PUT repos/a/b/pulls/5/merge -f commit_title=x",
        "gh api -X PUT repos/a/b/pulls/5/merge -F 'commit_title=15ב. x'",
        "gh api -X PUT repos/a/b/pulls/5/merge -fcommit_title=x",
        "gh api -X PUT repos/a/b/pulls/5/merge --raw-field commit_title=x",
        "gh api -X PUT repos/a/b/pulls/5/merge --field=commit_title=x",
        "cd repo && gh api -X PUT /repos/a/b/pulls/5/merge -f commit_title=x",
        'gh api -X PUT "repos/$REPO/pulls/$PR/merge" -f commit_title=x',
    ],
)
def test_api_merge_title_is_blocked(monkeypatch, command):
    code, reason = run_hook(monkeypatch, tool_call(command))
    assert code == 2
    assert "commit_title" in reason


@pytest.mark.parametrize(
    "command",
    [
        "gh api -X PUT repos/a/b/pulls/5/merge -f merge_method=squash",
        "gh api -X PUT repos/a/b/pulls/5/merge -f commit_message=commit_title=x",
        "gh api -X PATCH repos/a/b/pulls/5 -f title=x -f commit_title=y",
    ],
)
def test_api_merge_without_title_passes(monkeypatch, command):
    assert run_hook(monkeypatch, tool_call(command)) == (0, "")
