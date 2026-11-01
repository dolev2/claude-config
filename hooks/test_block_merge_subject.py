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
