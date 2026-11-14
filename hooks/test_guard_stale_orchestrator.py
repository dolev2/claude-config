"""guard_stale_orchestrator.py: a stale orchestrator opens no child, merges nothing."""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "guard_stale_orchestrator.py"
spec = importlib.util.spec_from_file_location("guard_stale_orchestrator", SCRIPT)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

SESSION = "s-1"
SKILL_CALL = {
    "type": "assistant",
    "message": {
        "content": [
            {"type": "tool_use", "name": "Skill", "input": {"skill": "dev-orchestrate"}}
        ]
    },
}
COMMAND_CALL = {
    "type": "user",
    "message": {
        "content": "<command-message>dev-orchestrate</command-message>\n"
        "<command-name>/dev-orchestrate</command-name>"
    },
}
# The name is in every session's text: the skill list, a child's contract.
NAME_ONLY = {
    "type": "user",
    "message": {"content": "- dev-orchestrate: Runs the whole current sprint"},
}
CHILD = {
    "tool_name": "mcp__claude-code-remote__create_session",
    "tool_input": {"tags": ["claude-config:orchestrated", "repo:dolev2/x"]},
}
NEW_ORCHESTRATOR = {
    "tool_name": "mcp__claude-code-remote__create_session",
    "tool_input": {"title": "x: מתזמר הספרינט"},
}
GH_MERGE = {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 5 --squash"}}
API_MERGE = {
    "tool_name": "Bash",
    "tool_input": {"command": "gh api -X PUT repos/dolev2/x/pulls/5/merge"},
}
MCP_MERGE = {"tool_name": "mcp__github__merge_pull_request", "tool_input": {}}


def git(cwd: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class Pipeline:
    """A local pipeline remote, its work clone, and the cache the guard reads."""

    def __init__(self, root: Path):
        self.remote = root / "remote.git"
        git(root, "init", "-q", "--bare", str(self.remote))
        self.work = root / "work"
        git(root, "clone", "-q", str(self.remote), str(self.work))
        self.baseline = self.commit("CLAUDE.md")
        self.cache = root / "home" / ".cache" / "claude-config-pipeline.git"
        self.cache.parent.mkdir(parents=True)
        git(root, "clone", "-q", "--bare", str(self.remote), str(self.cache))

    def commit(self, path: str) -> str:
        target = self.work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as file:
            file.write("x\n")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", path)
        git(self.work, "push", "-q", "origin", "main")
        return git(self.work, "rev-parse", "HEAD")


@pytest.fixture
def pipeline(tmp_path, monkeypatch) -> Pipeline:
    pipeline = Pipeline(tmp_path)
    monkeypatch.setattr(guard.pipeline_shas, "CACHE", pipeline.cache)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    return pipeline


def markers(tmp_path: Path) -> Path:
    return tmp_path / "tmp" / "claude-hooks"


def start_session(tmp_path: Path, baseline: str) -> None:
    folder = markers(tmp_path)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"session-start-{SESSION}").write_text(baseline, encoding="utf-8")


def transcript(tmp_path: Path, *entries: dict) -> str:
    path = tmp_path / "transcript.jsonl"
    lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def event(tmp_path: Path, call: dict, hook: str = "PreToolUse", *entries) -> dict:
    return {
        **call,
        "hook_event_name": hook,
        "session_id": SESSION,
        "transcript_path": transcript(tmp_path, *(entries or (SKILL_CALL,))),
    }


def run(monkeypatch, data: dict | str, capsys) -> tuple[int, str, str]:
    raw = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw.encode())))
    code = guard.main()
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def stale(pipeline, tmp_path) -> str:
    """An orchestrator session whose rules moved after it started; the moving sha."""
    start_session(tmp_path, pipeline.baseline)
    return pipeline.commit("rules/new.md")


def test_child_in_a_stale_orchestrator_is_blocked(monkeypatch, tmp_path, stale, capsys):
    code, out, err = run(monkeypatch, event(tmp_path, CHILD), capsys)

    assert code == 2
    assert out == ""
    assert stale in err
    assert "פתיחת בן נחסמה" in err
    assert "מתזמר חדש" in err


def test_new_orchestrator_passes(monkeypatch, tmp_path, stale, capsys):
    assert run(monkeypatch, event(tmp_path, NEW_ORCHESTRATOR), capsys) == (0, "", "")


@pytest.mark.parametrize("call", [GH_MERGE, API_MERGE, MCP_MERGE])
def test_merge_in_a_stale_orchestrator_is_blocked(
    monkeypatch, tmp_path, stale, capsys, call
):
    code, _, err = run(monkeypatch, event(tmp_path, call), capsys)

    assert code == 2
    assert "המיזוג נחסם" in err


def test_a_command_starts_an_orchestrator_too(monkeypatch, tmp_path, stale, capsys):
    data = event(tmp_path, GH_MERGE, "PreToolUse", COMMAND_CALL)

    assert run(monkeypatch, data, capsys)[0] == 2


def test_merge_in_a_regular_session_passes(monkeypatch, tmp_path, stale, capsys):
    data = event(tmp_path, GH_MERGE, "PreToolUse", NAME_ONLY)

    assert run(monkeypatch, data, capsys) == (0, "", "")


def test_a_change_only_in_skills_passes(monkeypatch, tmp_path, pipeline, capsys):
    start_session(tmp_path, pipeline.baseline)
    pipeline.commit("skills/x/SKILL.md")

    assert run(monkeypatch, event(tmp_path, CHILD), capsys) == (0, "", "")


def test_other_commands_pass(monkeypatch, tmp_path, stale, capsys):
    data = event(tmp_path, {"tool_name": "Bash", "tool_input": {"command": "ls"}})

    assert run(monkeypatch, data, capsys) == (0, "", "")


def test_no_baseline_marker_passes(monkeypatch, tmp_path, pipeline, capsys):
    pipeline.commit("rules/new.md")

    assert run(monkeypatch, event(tmp_path, CHILD), capsys) == (0, "", "")


def test_unknown_baseline_passes(monkeypatch, tmp_path, pipeline, capsys):
    start_session(tmp_path, "0" * 40)
    pipeline.commit("rules/new.md")

    assert run(monkeypatch, event(tmp_path, CHILD), capsys) == (0, "", "")


def test_git_failure_passes(monkeypatch, tmp_path, stale, capsys):
    def broken(cache):
        raise subprocess.CalledProcessError(128, "git")

    monkeypatch.setattr(guard.pipeline_shas, "refresh_cache", broken)

    assert run(monkeypatch, event(tmp_path, CHILD), capsys) == (0, "", "")


def test_outside_a_cloud_session_passes(monkeypatch, tmp_path, stale, capsys):
    monkeypatch.delenv("CLAUDE_CODE_REMOTE")

    assert run(monkeypatch, event(tmp_path, CHILD), capsys) == (0, "", "")


def test_input_that_is_not_json_passes(monkeypatch, pipeline, capsys):
    assert run(monkeypatch, "not json", capsys) == (0, "", "")


def stop_event(tmp_path: Path, *entries, active: bool = False) -> dict:
    data = event(tmp_path, {}, "Stop", *entries)
    return {**data, "stop_hook_active": active}


def test_stop_in_a_stale_orchestrator_is_blocked(monkeypatch, tmp_path, stale, capsys):
    code, out, _ = run(monkeypatch, stop_event(tmp_path), capsys)

    assert code == 0
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert stale in decision["reason"]


def test_stop_hook_active_passes(monkeypatch, tmp_path, stale, capsys):
    assert run(monkeypatch, stop_event(tmp_path, active=True), capsys) == (0, "", "")


def test_stop_after_the_hand_off_passes(monkeypatch, tmp_path, stale, capsys):
    run(monkeypatch, event(tmp_path, NEW_ORCHESTRATOR, "PostToolUse"), capsys)

    assert run(monkeypatch, stop_event(tmp_path), capsys) == (0, "", "")


def test_a_child_is_not_a_hand_off(monkeypatch, tmp_path, stale, capsys):
    run(monkeypatch, event(tmp_path, CHILD, "PostToolUse"), capsys)

    assert json.loads(run(monkeypatch, stop_event(tmp_path), capsys)[1])


def test_stop_in_a_regular_session_runs_no_git(monkeypatch, tmp_path, stale, capsys):
    def no_git(cache):
        raise AssertionError("git ran in a regular session")

    monkeypatch.setattr(guard.pipeline_shas, "refresh_cache", no_git)

    assert run(monkeypatch, stop_event(tmp_path, NAME_ONLY), capsys) == (0, "", "")


def test_the_hook_from_the_command_line(tmp_path, stale):
    data = event(tmp_path, CHILD)
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmp"),
        "CLAUDE_CODE_REMOTE": "true",
    }

    done = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(data).encode(),
        env=env,
        capture_output=True,
    )

    assert done.returncode == 2
    assert stale in done.stderr.decode("utf-8")
