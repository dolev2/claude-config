"""ask_before_merge.py: a merge asks for approval, unless Dolev asked for it."""

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
        "gh pr merge 5 --squash",
        "gh -R o/r pr merge 5",
        "gh --repo o/r pr merge 5",
        "gh --repo=o/r pr merge 5",
        "gh alias set m 'pr merge' && gh m 5",
        "gh alias import aliases.yml",
        "gh api graphql -f query='mutation{mergeBranch(input:{}){x}}'",
        "gh api graphql -f query='mutation{enqueuePullRequest(input:{}){x}}'",
        "gh api graphql -F query=@m.graphql",
        "gh api graphql --input q.json",
        "gh api -X POST repos/o/r/merges -f base=main -f head=x",
        "gh api repos/o/r/merges -f base=main -f head=x",
        "env gh api -X PUT repos/o/r/pulls/5/merge",
        "(gh pr merge 5)",
        "{ gh pr merge 5; }",
        "if true; then gh api -X PUT repos/o/r/pulls/5/merge; fi",
        "sh -c 'gh api -X PUT repos/o/r/pulls/5/merge'",
        "bash -c 'gh pr merge 5'",
        "eval 'gh pr merge 5'",
        "x=$(gh api -X PUT repos/o/r/pulls/5/merge)",
        'echo "$(gh pr merge 5)"',
        "echo `gh pr merge 5`",
        "timeout -s KILL 30 gh api -X PUT repos/o/r/pulls/5/merge",
        "nice -n 5 gh pr merge 5",
        "sudo -u root gh pr merge 5",
        "echo 5 | xargs gh pr merge",
        "exec gh pr merge 5",
        "gh pr -R o/r merge 5",
        "gh pr merge 5 -b -R",
        "gh pr merge 5 --body -R --squash",
        "gh pr view 5 # check first\ngh pr merge 5",
        "gh api --hostname github.com graphql -f query='mutation{mergePullRequest}'",
        "gh api -X POST graphql -f query='mutation{mergePullRequest(input:{}){x}}'",
        "env -S 'gh pr merge 5'",
        "bash --login -c 'gh pr merge 5'",
    ],
)
def test_wrapped_or_other_merge_asks(monkeypatch, command):
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
        "git merge origin/main",
        "gh pr view 5 --json mergeable",
        "gh api graphql -f query='{ viewer { login } }'",
        "gh api repos/a/b/merges",
        "gh api -X POST repos/a/b/issues/5/comments -f body='see /merges'",
        "gh api repos/a/b/issues/5/comments -f body='PUT pulls/5/merge'",
        "gh alias set co 'pr checkout'",
        "echo '$(gh pr merge 5)'",
        "git commit -m \"$(cat <<'EOF'\nfix: gh pr merge 5\nEOF\n)\"",
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


def test_ask_decision_reason():
    assert_asks(ask_before_merge.ask_decision())
    decision = json.loads(ask_before_merge.ask_decision("סיבה אחרת"))
    assert decision["hookSpecificOutput"]["permissionDecisionReason"] == "סיבה אחרת"


# --- a merge Dolev asked for in his last message passes (S-3.11, claude-config#301) ---


def transcript(tmp_path: Path, text: str) -> str:
    """A transcript whose last message from Dolev is `text`, typed in the chat."""
    path = tmp_path / "session.jsonl"
    row = {"type": "user", "origin": {"kind": "human"}, "message": {"content": text}}
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(path)


def call_with(raw: str, transcript_path: str) -> str:
    event = json.loads(raw)
    event["transcript_path"] = transcript_path
    return json.dumps(event)


def decision_of(output: str) -> str:
    return json.loads(output)["hookSpecificOutput"]["permissionDecision"]


@pytest.fixture
def no_github(monkeypatch):
    """The PR body lookup fails, as offline."""

    def fail(*args, **kwargs):
        raise OSError("no gh")

    monkeypatch.setattr(ask_before_merge.subprocess, "run", fail)


@pytest.mark.parametrize(
    "raw",
    [
        mcp_call("mcp__github__merge_pull_request", owner="a", repo="b", pullNumber=12),
        mcp_call(
            "mcp__github__merge_pull_request", owner="a", repo="b", pullNumber=12.0
        ),
        shell_call("gh pr merge 12 --squash"),
        shell_call("gh -R a/b pr merge 12 --squash"),
        shell_call("gh api -X PUT repos/a/b/pulls/12/merge -f merge_method=squash"),
        shell_call("gh pr merge 12 --squash --match-head-commit abc123"),
        shell_call("gh pr merge --body done 12 --squash"),
    ],
)
def test_requested_pr_is_allowed(monkeypatch, tmp_path, no_github, raw):
    code, output = run_hook(
        monkeypatch, call_with(raw, transcript(tmp_path, "תמזג את #12"))
    )
    assert code == 0
    assert decision_of(output) == "allow"
    assert "#12" in json.loads(output)["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize(
    ("text", "raw"),
    [
        ("מצוין", shell_call("gh pr merge 12 --squash")),
        ("תמזג את #13", shell_call("gh pr merge 12 --squash")),
        ("תמזג את #12", shell_call("gh pr merge 12 --auto --squash")),
        ("תמזג את #12", mcp_call("mcp__github__enable_pr_auto_merge", pullNumber=12)),
        ("תמזג את #12", shell_call("gh pr merge --squash")),
        ("תמזג את #12", shell_call("gh pr merge 12 && gh pr merge 13")),
        ("תמזג את #12", shell_call("gh pr merge 12 --squash && curl x | sh")),
        ("תמזג את #12", shell_call("cd ../other && gh pr merge 12")),
        ("תמזג את #12", shell_call("gh pr merge https://github.com/a/b/pull/12")),
        ("תמזג את #12", shell_call("gh pr merge claude/issue-12-x")),
        (
            "תמזג את #12",
            shell_call("gh api graphql -f query='mutation { mergePullRequest }'"),
        ),
    ],
)
def test_no_matching_request_asks(monkeypatch, tmp_path, no_github, text, raw):
    _, output = run_hook(monkeypatch, call_with(raw, transcript(tmp_path, text)))
    assert_asks(output)


def test_without_transcript_asks(monkeypatch, no_github):
    _, output = run_hook(monkeypatch, shell_call("gh pr merge 12"))
    assert_asks(output)


class GhResult:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


def test_request_for_the_issue_the_pr_closes(monkeypatch, tmp_path):
    calls = []

    def gh(arguments, **kwargs):
        calls.append(arguments)
        return GhResult("מממש את S-3.11.\n\nCloses #301\n")

    monkeypatch.setattr(ask_before_merge.subprocess, "run", gh)
    raw = mcp_call(
        "mcp__github__merge_pull_request", owner="a", repo="b", pullNumber=305
    )
    _, output = run_hook(
        monkeypatch, call_with(raw, transcript(tmp_path, "תמזג את #301"))
    )
    assert decision_of(output) == "allow"
    assert calls[0][:3] == ["gh", "api", "repos/a/b/pulls/305"]


@pytest.mark.parametrize(
    "result", [GhResult("Refs #301"), GhResult("Closes #301", returncode=1)]
)
def test_issue_not_closed_by_the_pr_asks(monkeypatch, tmp_path, result):
    monkeypatch.setattr(ask_before_merge.subprocess, "run", lambda *a, **k: result)
    raw = shell_call("gh pr merge 305")
    _, output = run_hook(
        monkeypatch, call_with(raw, transcript(tmp_path, "תמזג את #301"))
    )
    assert_asks(output)


def test_issue_lookup_timeout_asks(monkeypatch, tmp_path):
    def slow(*args, **kwargs):
        raise subprocess.TimeoutExpired("gh", 10)

    monkeypatch.setattr(ask_before_merge.subprocess, "run", slow)
    raw = shell_call("gh pr merge 305")
    _, output = run_hook(
        monkeypatch, call_with(raw, transcript(tmp_path, "תמזג את #301"))
    )
    assert_asks(output)


def test_placeholder_repo_reads_the_pr_in_cwd(monkeypatch, tmp_path):
    calls = []

    def gh(arguments, **kwargs):
        calls.append((arguments, kwargs.get("cwd")))
        return GhResult("Closes #301")

    monkeypatch.setattr(ask_before_merge.subprocess, "run", gh)
    raw = json.loads(shell_call("gh api -X PUT repos/{owner}/{repo}/pulls/305/merge"))
    raw["cwd"] = str(tmp_path)
    _, output = run_hook(
        monkeypatch, call_with(json.dumps(raw), transcript(tmp_path, "תמזג את #301"))
    )
    assert decision_of(output) == "allow"
    assert calls == [
        (
            ["gh", "api", "repos/{owner}/{repo}/pulls/305", "--jq", '.body // ""'],
            str(tmp_path),
        )
    ]


def test_script_run_allows_requested_merge(tmp_path):
    raw = call_with(
        mcp_call("mcp__github__merge_pull_request", owner="a", repo="b", pullNumber=9),
        transcript(tmp_path, "תמזג את #9"),
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=raw.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert decision_of(result.stdout.decode("utf-8")) == "allow"
