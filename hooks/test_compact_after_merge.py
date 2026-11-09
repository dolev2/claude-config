"""compact_after_merge.py: after a PR merge, the turn does not end without /compact."""

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "compact_after_merge.py"
spec = importlib.util.spec_from_file_location("compact_after_merge", SCRIPT)
compact_after_merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compact_after_merge)

WITH_BLOCK = "סיכום.\n\n**מה פתוח**\n\n```\n/compact מוזג #5, אין פתוח\n```\n"
INLINE_ONLY = "סיכום. כדאי להריץ `/compact` עכשיו.\n"


class FakeStream:
    """A stdin or stdout stand-in with the `.buffer` the hook reads and writes."""

    def __init__(self, data: bytes = b"") -> None:
        self.buffer = io.BytesIO(data)

    def flush(self) -> None:
        pass


@pytest.fixture
def markers(tmp_path, monkeypatch) -> Path:
    """The markers folder of the test, in tmp_path."""
    folder = tmp_path / "claude-hooks"
    monkeypatch.setattr(compact_after_merge, "marker_dir", lambda: folder)
    return folder


def run_hook(monkeypatch, raw: str) -> tuple[int, str]:
    """Run main() on raw stdin text; return the exit code and what went to stdout."""
    stdout = FakeStream()
    monkeypatch.setattr(sys, "stdin", FakeStream(raw.encode("utf-8")))
    monkeypatch.setattr(sys, "stdout", stdout)
    code = compact_after_merge.main()
    return code, stdout.buffer.getvalue().decode("utf-8")


def tool_event(tool: str, session: str = "s-1", turn: str = "p-1", **tool_input) -> str:
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "session_id": session,
            "prompt_id": turn,
            "tool_name": tool,
            "tool_input": tool_input,
        }
    )


def shell_event(command: str, session: str = "s-1", turn: str = "p-1") -> str:
    return tool_event("Bash", session, turn, command=command)


def stop_event(
    message: str, session: str = "s-1", active: bool = False, turn: str = "p-1"
) -> str:
    return json.dumps(
        {
            "hook_event_name": "Stop",
            "session_id": session,
            "prompt_id": turn,
            "stop_hook_active": active,
            "last_assistant_message": message,
        }
    )


@pytest.mark.parametrize(
    "raw",
    [
        tool_event("mcp__github__merge_pull_request", pullNumber=5),
        tool_event("mcp__claude_ai_GitHub__merge_pull_request", pullNumber=5),
        shell_event("gh pr merge 5 --squash"),
        shell_event("gh -R a/b pr merge 5 --squash"),
        shell_event("gh api -X PUT repos/a/b/pulls/5/merge -f merge_method=squash"),
        tool_event("PowerShell", command="gh pr merge 5 --squash"),
    ],
)
def test_merge_marks_and_reminds(monkeypatch, markers, raw):
    code, output = run_hook(monkeypatch, raw)
    assert code == 0
    context = json.loads(output)["hookSpecificOutput"]
    assert context["hookEventName"] == "PostToolUse"
    assert "/compact" in context["additionalContext"]
    assert (markers / "compact-s-1").exists()


@pytest.mark.parametrize(
    "raw",
    [
        shell_event("gh pr view 5"),
        shell_event("gh pr merge 5 --auto --squash"),
        shell_event("gh api repos/a/b/pulls/5/merge"),
        shell_event("gh alias set m 'pr merge'"),
        tool_event("mcp__github__enable_pr_auto_merge", pullNumber=5),
        tool_event("mcp__github__pull_request_read", pullNumber=5),
    ],
)
def test_other_call_leaves_no_marker(monkeypatch, markers, raw):
    assert run_hook(monkeypatch, raw) == (0, "")
    assert not markers.exists() or not any(markers.iterdir())


def test_stop_without_marker_passes(monkeypatch, markers):
    assert run_hook(monkeypatch, stop_event(INLINE_ONLY)) == (0, "")


def test_stop_with_block_clears_marker(monkeypatch, markers):
    run_hook(monkeypatch, shell_event("gh pr merge 5"))
    assert run_hook(monkeypatch, stop_event(WITH_BLOCK)) == (0, "")
    assert not (markers / "compact-s-1").exists()


@pytest.mark.parametrize("message", [INLINE_ONLY, "", "```\necho hi\n```\n"])
def test_stop_without_block_is_blocked_once(monkeypatch, markers, message):
    run_hook(monkeypatch, shell_event("gh pr merge 5"))
    code, output = run_hook(monkeypatch, stop_event(message))
    assert code == 0
    decision = json.loads(output)
    assert decision["decision"] == "block"
    assert "/compact" in decision["reason"]
    assert (markers / "compact-s-1").exists()
    # The second stop in the same turn ends it: one note, never a loop.
    assert run_hook(monkeypatch, stop_event(message, active=True)) == (0, "")
    assert not (markers / "compact-s-1").exists()


def test_block_with_tilde_fence_counts(monkeypatch, markers):
    run_hook(monkeypatch, shell_event("gh pr merge 5"))
    assert run_hook(monkeypatch, stop_event("~~~text\n/compact סיכום\n~~~\n")) == (
        0,
        "",
    )


def test_marker_of_an_earlier_turn_is_dropped(monkeypatch, markers):
    # A turn that merged and ended without Stop (an interrupt) leaves its marker.
    run_hook(monkeypatch, shell_event("gh pr merge 5", turn="p-1"))
    assert run_hook(monkeypatch, stop_event(INLINE_ONLY, turn="p-2")) == (0, "")
    assert not (markers / "compact-s-1").exists()


def test_event_without_prompt_id_still_checks(monkeypatch, markers):
    raw = json.loads(shell_event("gh pr merge 5"))
    del raw["prompt_id"]
    run_hook(monkeypatch, json.dumps(raw))
    code, output = run_hook(monkeypatch, stop_event(INLINE_ONLY))
    assert json.loads(output)["decision"] == "block"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (WITH_BLOCK, True),
        ("```bash\n\n/compact סיכום\n```", True),
        ("```\nls\n```\n/compact סיכום\n", False),
        ("```\nls\n/compact\n```", False),
        (INLINE_ONLY, False),
        (None, False),
    ],
)
def test_has_compact_block(message, expected):
    assert compact_after_merge.has_compact_block(message) is expected


def test_sessions_are_separate(monkeypatch, markers):
    run_hook(monkeypatch, shell_event("gh pr merge 5", session="s-1"))
    assert run_hook(monkeypatch, stop_event(INLINE_ONLY, session="s-2")) == (0, "")
    assert (markers / "compact-s-1").exists()


def test_session_id_is_sanitized(markers):
    event = {"session_id": "../../etc/x"}
    assert compact_after_merge.marker_path(event) == markers / "compact-etcx"


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[1, 2]",
        json.dumps({"hook_event_name": "Stop", "stop_hook_active": False}),
        json.dumps({"hook_event_name": "PostToolUse", "session_id": "///"}),
    ],
)
def test_bad_input_passes(monkeypatch, markers, raw):
    assert run_hook(monkeypatch, raw) == (0, "")


def test_unwritable_marker_passes(monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setattr(compact_after_merge, "marker_dir", lambda: blocker / "x")
    assert run_hook(monkeypatch, shell_event("gh pr merge 5")) == (0, "")


def test_script_runs_end_to_end(tmp_path):
    env = {**os.environ, "TMPDIR": str(tmp_path), "TMP": str(tmp_path)}

    def run(raw: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=raw.encode("utf-8"),
            capture_output=True,
            env=env,
            check=False,
        )

    merged = run(shell_event("gh pr merge 5"))
    assert merged.returncode == 0
    assert "additionalContext" in merged.stdout.decode("utf-8")
    stopped = run(stop_event(INLINE_ONLY))
    assert stopped.returncode == 0
    assert json.loads(stopped.stdout)["decision"] == "block"
    assert run(stop_event(WITH_BLOCK)).stdout == b""
