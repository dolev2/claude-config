"""guard_create_session.py: a child with broad grants opens an approval window."""

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "guard_create_session.py"
spec = importlib.util.spec_from_file_location("guard_create_session", SCRIPT)
guard_create_session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard_create_session)

TOOL = "mcp__claude-code-remote__create_session"
CHILD_TOOLS = sorted(guard_create_session.CHILD_TOOLS)


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
    code = guard_create_session.main()
    return code, stdout.buffer.getvalue().decode("utf-8")


def call(tool: str = TOOL, **tool_input) -> str:
    return json.dumps({"tool_name": tool, "tool_input": tool_input})


def ask_reason(output: str) -> str:
    decision = json.loads(output)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "ask"
    return decision["permissionDecisionReason"]


@pytest.mark.parametrize(
    "tool_input",
    [
        {},
        {"prompt": "work on #5", "title": "claude/issue-5-x"},
        {"extra_allowed_tools": []},
        {"extra_allowed_tools": CHILD_TOOLS},
        {"extra_allowed_tools": CHILD_TOOLS[:1], "environment_id": ""},
    ],
)
def test_orchestrator_child_passes(monkeypatch, tool_input):
    assert run_hook(monkeypatch, call(**tool_input)) == (0, "")


@pytest.mark.parametrize(
    "tool",
    [
        "Bash(git push:*)",
        "*",
        "mcp__github__merge_pull_request",
        "mcp__github__delete_file",
    ],
)
def test_broad_tool_asks_and_names_it(monkeypatch, tool):
    raw = call(extra_allowed_tools=[*CHILD_TOOLS, tool])
    code, output = run_hook(monkeypatch, raw)
    assert code == 0
    reason = ask_reason(output)
    assert f"`{tool}`" in reason
    assert not any(child in reason for child in CHILD_TOOLS)


def test_environment_id_asks(monkeypatch):
    code, output = run_hook(monkeypatch, call(environment_id="env_abc"))
    assert code == 0
    assert "env_abc" in ask_reason(output)


def test_every_catch_is_listed(monkeypatch):
    raw = call(extra_allowed_tools=["Bash(ls)", "*"], environment_id="env_abc")
    reason = ask_reason(run_hook(monkeypatch, raw)[1])
    assert "1. " in reason and "2. " in reason and "3. " in reason


def test_lone_string_is_one_tool(monkeypatch):
    reason = ask_reason(run_hook(monkeypatch, call(extra_allowed_tools="*"))[1])
    assert "`*`" in reason


@pytest.mark.parametrize(
    "tool",
    ["mcp__github__create_pull_request", "mcp__claude-code-remote__send_message"],
)
def test_other_tool_passes(monkeypatch, tool):
    assert run_hook(monkeypatch, call(tool, extra_allowed_tools=["*"])) == (0, "")


def test_other_server_name_is_checked(monkeypatch):
    raw = call("mcp__abc123__create_session", extra_allowed_tools=["*"])
    assert "`*`" in ask_reason(run_hook(monkeypatch, raw)[1])


@pytest.mark.parametrize(
    "raw",
    ["", "not json", "[]", json.dumps({"tool_name": TOOL, "tool_input": "x"})],
)
def test_unreadable_input_passes(monkeypatch, raw):
    assert run_hook(monkeypatch, raw) == (0, "")


def test_script_run_prints_the_decision():
    raw = call(extra_allowed_tools=["Bash(git push:*)"])
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=raw.encode("utf-8"),
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0
    assert "Bash(git push:*)" in ask_reason(result.stdout.decode("utf-8"))
