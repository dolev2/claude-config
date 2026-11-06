"""ask_before_merge.py: a PR merge other than `gh pr merge` opens an approval window."""

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "ask_before_merge.py"
spec = importlib.util.spec_from_file_location("ask_before_merge", SCRIPT)
ask_before_merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ask_before_merge)


class FakeStream:
    """A stdin or stdout stand-in with the `.buffer` the hook reads and writes."""

    def __init__(self, data: bytes = b"") -> None:
        self.buffer = io.BytesIO(data)

    def flush(self) -> None:
        pass


def run_hook(monkeypatch, raw: str) -> tuple[int, str]:
    """Run main() on raw stdin text; return the exit code and what went to stdout."""
    stdout = FakeStream()
    monkeypatch.setattr(sys, "stdin", FakeStream(raw.encode("utf-8")))
    monkeypatch.setattr(sys, "stdout", stdout)
    code = ask_before_merge.main()
    return code, stdout.buffer.getvalue().decode("utf-8")


def shell_call(command: str, tool: str = "Bash") -> str:
    return json.dumps({"tool_name": tool, "tool_input": {"command": command}})


def mcp_call(tool: str, **tool_input) -> str:
    return json.dumps({"tool_name": tool, "tool_input": tool_input})


def assert_asks(output: str) -> None:
    decision = json.loads(output)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "ask"
    assert "דולב" in decision["permissionDecisionReason"]


@pytest.mark.parametrize(
    "tool",
    [
        "mcp__github__merge_pull_request",
        "mcp__github__enable_pr_auto_merge",
        "mcp__claude_ai_GitHub__merge_pull_request",
        "mcp__1a2b3c__enable_pr_auto_merge",
    ],
)
def test_mcp_merge_asks(monkeypatch, tool):
    code, output = run_hook(monkeypatch, mcp_call(tool, owner="a", repo="b"))
    assert code == 0
    assert_asks(output)


@pytest.mark.parametrize(
    "tool",
    [
        "mcp__github__pull_request_read",
        "mcp__github__disable_pr_auto_merge",
        "mcp__github__update_pull_request_branch",
        "merge_pull_request",
        "Edit",
    ],
)
def test_other_tools_pass(monkeypatch, tool):
    assert run_hook(monkeypatch, mcp_call(tool, command="x")) == (0, "")


@pytest.mark.parametrize(
    "command",
    [
        "gh api -X PUT repos/a/b/pulls/5/merge -f merge_method=squash",
        "gh api --method PUT repos/{owner}/{repo}/pulls/5/merge",
        "gh api --method=put /repos/a/b/pulls/5/merge",
        "gh api -XPUT repos/a/b/pulls/5/merge",
        "gh api repos/a/b/pulls/5/merge -X PUT",
        "gh api -X PUT https://api.github.com/repos/a/b/pulls/5/merge",
        "git fetch origin main && gh api -X PUT repos/a/b/pulls/5/merge",
        "GH_REPO=a/b gh api -X PUT repos/a/b/pulls/5/merge",
        "gh.exe api -X PUT repos/a/b/pulls/5/merge",
        'gh api -X PUT "repos/$REPO/pulls/$PR/merge"',
        "gh api -X PUT repos/{owner}/{repo}/pulls/${N}/merge",
        "gh api graphql -f query='mutation { mergePullRequest(input: {}) { x } }'",
        "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input: {}) }'",
    ],
)
def test_api_merge_asks(monkeypatch, command):
    code, output = run_hook(monkeypatch, shell_call(command))
    assert code == 0
    assert_asks(output)


@pytest.mark.parametrize(
    "command",
    [
        "gh api repos/a/b/pulls/5/merge",
        "gh api -X GET repos/a/b/pulls/5/merge",
        "gh api -X PUT repos/a/b/pulls/5/requested_reviewers",
        "gh api -X PUT repos/a/b/pulls/5/merge_requests",
        "gh api graphql -f query='{ repository { pullRequest { mergeable } } }'",
        "gh pr merge 5 --squash",
        "git merge origin/main",
        "echo gh api -X PUT repos/a/b/pulls/5/merge",
        "cat > notes.md <<'EOF'\ngh api -X PUT repos/a/b/pulls/5/merge\nEOF",
    ],
)
def test_other_commands_pass(monkeypatch, command):
    assert run_hook(monkeypatch, shell_call(command)) == (0, "")


def test_powershell_command_is_checked(monkeypatch):
    raw = shell_call("gh api -X PUT repos/a/b/pulls/5/merge; echo done", "PowerShell")
    code, output = run_hook(monkeypatch, raw)
    assert code == 0
    assert_asks(output)


@pytest.mark.parametrize("raw", ["", "not json", "[]", '{"tool_name": "Bash"}'])
def test_unreadable_input_passes(monkeypatch, raw):
    assert run_hook(monkeypatch, raw) == (0, "")


def test_script_run_prints_the_decision():
    raw = mcp_call("mcp__github__merge_pull_request", owner="a", repo="b")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=raw.encode("utf-8"),
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert_asks(result.stdout.decode("utf-8"))
