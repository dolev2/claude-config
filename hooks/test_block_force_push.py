"""block_force_push.py: force pushes are blocked, lease pushes and the rest pass."""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "block_force_push.py"
spec = importlib.util.spec_from_file_location("block_force_push", SCRIPT)
block_force_push = importlib.util.module_from_spec(spec)
spec.loader.exec_module(block_force_push)


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
    code = block_force_push.main()
    return code, stderr.buffer.getvalue().decode("utf-8")


def tool_call(command: str, tool: str = "Bash") -> str:
    return json.dumps({"tool_name": tool, "tool_input": {"command": command}})


@pytest.mark.parametrize(
    "command",
    [
        "git push --force",
        "git push -f origin feature",
        "git push -fu origin feature",
        "git push origin +main",
        "git push origin +HEAD:main",
        "git push origin main --force",
        "git -C repo push --force",
        "git -c core.x=y --no-pager push -f",
        "cd repo && git push --force",
        "git status; git push -f",
        "git add .\ngit push --force",
        "git push --force --force-with-lease",
        "GIT_TRACE=1 git push -f",
        "timeout 30 git push --force",
        "/usr/bin/git push -f",
        "git push -o ci.skip -f",
        "git push -- +main",
        "git push --mirror",
        "git push --mirror origin",
        "git send-pack --force origin main",
        "git send-pack origin +main",
        "env git push -f",
        "env -i PATH=/bin git push -f",
        "exec git push -f",
        "echo x | xargs git push -f",
        "(git push -f)",
        "{ git push -f; }",
        "if true; then git push -f; fi",
        "y=$(git push -f)",
        'echo "$(git push -f)"',
        "echo `git push -f`",
        "sh -c 'git push -f'",
        "bash -c 'git push -f'",
        "bash -lc 'git push -f'",
        "eval 'git push -f'",
        "nice -n 5 git push -f",
        "timeout -s KILL 30 git push -f",
        "sudo -u root git push -f",
    ],
)
def test_force_push_is_blocked(monkeypatch, command):
    code, reason = run_hook(monkeypatch, tool_call(command))
    assert code == 2
    assert "--force-with-lease" in reason


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push -u origin feature",
        "git push --force-with-lease",
        "git push --force-with-lease=main:abc123",
        "git push --force-if-includes --force-with-lease",
        "git push -o force origin feature",
        "git push -oforce origin feature",
        'git commit -m "--force"',
        'git commit -m "a; git push -f"',
        "echo git push --force",
        "git log --format=%H | grep push",
        "ls -f",
        "cat > notes.md <<'EOF'\ngit push --force\nEOF",
        "(git push --force-with-lease)",
        "env GIT_TRACE=1 git push --force-with-lease",
        "if true; then git push; fi",
        "bash -c 'git push -u origin feature'",
        "echo '$(git push -f)'",
        "git commit -m \"$(cat <<'EOF'\nfix: git push -f\nEOF\n)\"",
        "git send-pack origin main",
        # Not read, by decision (claude-config#163): config set on the command line.
        "git -c alias.p='push --force' p",
        "git -c remote.origin.push=+HEAD:main push",
    ],
)
def test_other_commands_pass(monkeypatch, command):
    assert run_hook(monkeypatch, tool_call(command)) == (0, "")


def test_powershell_command_is_checked(monkeypatch):
    code, _ = run_hook(monkeypatch, tool_call("git push -f; echo done", "PowerShell"))
    assert code == 2


def test_other_tools_pass(monkeypatch):
    raw = json.dumps({"tool_name": "Edit", "tool_input": {"command": "git push -f"}})
    assert run_hook(monkeypatch, raw) == (0, "")


@pytest.mark.parametrize("raw", ["", "not json", "[]", '{"tool_name": "Bash"}'])
def test_unreadable_input_passes(monkeypatch, raw):
    assert run_hook(monkeypatch, raw) == (0, "")


def test_open_quote_still_checked(monkeypatch):
    code, _ = run_hook(monkeypatch, tool_call("git push -f && echo 'unclosed"))
    assert code == 2
