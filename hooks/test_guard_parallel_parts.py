"""guard_parallel_parts.py: an agent in parallel work edits only its own part's files.

Each test builds a small repo with a task worktree and two agent worktrees under
.claude/worktrees/, made by `git worktree add` so each git dir is
`<common>/worktrees/agent-<id>`, like the Agent tool makes them.
"""

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "guard_parallel_parts.py"
spec = importlib.util.spec_from_file_location("guard_parallel_parts", SCRIPT)
guard_parallel_parts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard_parallel_parts)

AGENT = "a1"
OTHER_AGENT = "b2"
PARTS = {
    "issue": 82,
    "branch": "claude/issue-82-parallel-prefix-guard",
    "start": "0" * 40,
    "parts": {
        "hook": ["hooks/", "README.md", "skills/dev-setup/reference/issue-lifecycle"],
        "skills": ["skills/dev-code/"],
    },
}


class FakeStream:
    """A stdin or stderr stand-in with the `.buffer` the hook reads and writes."""

    def __init__(self, data: bytes = b"") -> None:
        self.buffer = io.BytesIO(data)

    def flush(self) -> None:
        pass


def git(folder: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@t"]
        + list(arguments),
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path) -> Path:
    """A repo with a parts file, a task worktree and two registered agent worktrees."""
    main = (tmp_path / "repo").resolve()
    (main / "hooks").mkdir(parents=True)
    (main / "hooks" / "guard.py").write_text("x\n")
    (main / "README.md").write_text("readme\n")
    git(main, "init", "-q", "-b", "main")
    git(main, "add", ".")
    git(main, "commit", "-q", "-m", "init")
    git(main, "worktree", "add", "-q", str(main / ".claude" / "worktrees" / "task"))
    for agent, part in ((AGENT, "hook"), (OTHER_AGENT, "skills")):
        folder = main / ".claude" / "worktrees" / f"agent-{agent}"
        git(main, "worktree", "add", "-q", "-b", f"worktree-agent-{agent}", str(folder))
        registration(main, agent).write_text(f"{part}\n")
    parts_file(main).write_text(json.dumps(PARTS))
    return main


def parts_file(main: Path) -> Path:
    return main / ".git" / "parallel-parts.json"


def registration(main: Path, agent: str = AGENT) -> Path:
    return main / ".git" / "worktrees" / f"agent-{agent}" / "parallel-part"


def worktree(main: Path, agent: str = AGENT) -> Path:
    return main / ".claude" / "worktrees" / f"agent-{agent}"


def run_hook(monkeypatch, event: dict | str) -> tuple[int, str]:
    """Run main() on the event as stdin; return the exit code and stderr."""
    raw = event if isinstance(event, str) else json.dumps(event)
    stderr = FakeStream()
    monkeypatch.setattr(sys, "stdin", FakeStream(raw.encode("utf-8")))
    monkeypatch.setattr(sys, "stderr", stderr)
    code = guard_parallel_parts.main()
    return code, stderr.buffer.getvalue().decode("utf-8")


def edit(path: Path, tool: str = "Edit", agent: str | None = AGENT, cwd=None) -> dict:
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    event = {
        "tool_name": tool,
        "tool_input": {key: str(path)},
        "cwd": str(cwd or path.parent),
    }
    if agent is not None:
        event["agent_id"] = agent
    return event


@pytest.mark.parametrize(
    ("relative", "tool"),
    [
        ("hooks/guard.py", "Edit"),
        ("hooks/new/deep/file.py", "Write"),
        ("README.md", "MultiEdit"),
        ("hooks/notes.ipynb", "NotebookEdit"),
    ],
)
def test_edit_inside_prefixes_passes(monkeypatch, repo, relative, tool):
    assert run_hook(monkeypatch, edit(worktree(repo) / relative, tool)) == (0, "")


@pytest.mark.parametrize(
    "relative", ["settings.json", "skills/dev-code/SKILL.md", "hooks_old/x.py"]
)
def test_edit_outside_prefixes_in_own_worktree_is_blocked(monkeypatch, repo, relative):
    code, reason = run_hook(monkeypatch, edit(worktree(repo) / relative, "Write"))
    assert code == 2
    assert "בקשה לסשן הראשי" in reason
    assert "`hooks/`" in reason
    assert "`README.md`" in reason


@pytest.mark.parametrize(
    "relative",
    [
        "skills/dev-setup/reference/issue-lifecycle.html",
        "skills/dev-setup/reference/issue-lifecycle-en.html",
        "README.md.bak",
    ],
)
def test_prefix_without_slash_covers_every_path_that_starts_with_it(
    monkeypatch, repo, relative
):
    assert run_hook(monkeypatch, edit(worktree(repo) / relative, "Write")) == (0, "")


@pytest.mark.parametrize(
    "relative", ["docs/README.md", "skills/dev-setup/reference/diagram.md"]
)
def test_path_that_does_not_start_with_a_prefix_is_blocked(monkeypatch, repo, relative):
    code, _reason = run_hook(monkeypatch, edit(worktree(repo) / relative, "Write"))
    assert code == 2


@pytest.mark.parametrize("blank", ["", " "])
def test_blank_prefix_covers_nothing(monkeypatch, repo, blank):
    data = {**PARTS, "parts": {**PARTS["parts"], "hook": ["hooks/", blank]}}
    parts_file(repo).write_text(json.dumps(data))
    code, _reason = run_hook(monkeypatch, edit(worktree(repo) / "settings.json"))
    assert code == 2


def test_other_agent_is_judged_by_its_own_part(monkeypatch, repo):
    other = worktree(repo, OTHER_AGENT)
    allowed = edit(other / "skills/dev-code/SKILL.md", agent=OTHER_AGENT)
    blocked = edit(other / "hooks/guard.py", agent=OTHER_AGENT)
    assert run_hook(monkeypatch, allowed) == (0, "")
    assert run_hook(monkeypatch, blocked)[0] == 2


@pytest.mark.parametrize("target", ["parts", "registration", "config"])
def test_edit_inside_git_common_dir_is_blocked(monkeypatch, repo, target):
    paths = {
        "parts": parts_file(repo),
        "registration": registration(repo),
        "config": repo / ".git" / "config",
    }
    code, reason = run_hook(monkeypatch, edit(paths[target], "Write"))
    assert code == 2
    assert "בקשה לסשן הראשי" in reason


@pytest.mark.parametrize(
    "folder",
    [".", ".claude/worktrees/task", f".claude/worktrees/agent-{OTHER_AGENT}"],
)
def test_edit_in_another_worktree_is_blocked(monkeypatch, repo, folder):
    code, reason = run_hook(monkeypatch, edit(repo / folder / "hooks" / "guard.py"))
    assert code == 2
    assert "בקשה לסשן הראשי" in reason


@pytest.mark.parametrize(
    ("place", "marker"),
    [
        ("outside_part", "מחוץ לחלק"),
        ("git_dir", "בתיקיית ה-git המשותפת"),
        ("other_worktree", "בעותק אחר של הריפו"),
    ],
)
def test_every_block_forbids_a_bypass(monkeypatch, repo, place, marker):
    targets = {
        "outside_part": worktree(repo) / "settings.json",
        "git_dir": parts_file(repo),
        "other_worktree": repo / "hooks" / "guard.py",
    }
    code, reason = run_hook(monkeypatch, edit(targets[place], "Write"))
    assert code == 2
    assert marker in reason
    assert "בקשה לסשן הראשי" in reason
    assert "לא עוקפים את החסימה" in reason
    assert "גם כשהיא נראית לך שגויה" in reason


def test_edit_outside_repo_passes(monkeypatch, repo, tmp_path):
    scratch = tmp_path / "scratchpad" / "notes" / "plan.txt"
    assert run_hook(monkeypatch, edit(scratch, "Write")) == (0, "")


def test_no_agent_id_is_no_decision(monkeypatch, repo):
    event = edit(repo / "settings.json", agent=None)
    assert run_hook(monkeypatch, event) == (0, "")


def test_no_parts_file_is_no_decision(monkeypatch, repo):
    parts_file(repo).unlink()
    assert run_hook(monkeypatch, edit(worktree(repo) / "settings.json")) == (0, "")


def test_no_registration_is_no_decision(monkeypatch, repo):
    registration(repo).unlink()
    assert run_hook(monkeypatch, edit(worktree(repo) / "settings.json")) == (0, "")


def test_unregistered_agent_id_is_no_decision(monkeypatch, repo):
    event = edit(repo / "settings.json", agent="unknown")
    assert run_hook(monkeypatch, event) == (0, "")


def test_registration_to_unknown_part_is_blocked(monkeypatch, repo):
    registration(repo).write_text("docs\n")
    code, reason = run_hook(monkeypatch, edit(worktree(repo) / "hooks" / "guard.py"))
    assert code == 2
    assert "`docs`" in reason
    assert "`hook`" in reason
    assert "`skills`" in reason


@pytest.mark.parametrize("cwd_place", ["main", "outside"])
def test_cwd_does_not_change_the_decision(monkeypatch, repo, tmp_path, cwd_place):
    cwd = repo if cwd_place == "main" else tmp_path
    monkeypatch.chdir(cwd)
    allowed = edit(worktree(repo) / "hooks" / "guard.py", cwd=cwd)
    blocked = edit(worktree(repo) / "settings.json", cwd=cwd)
    assert run_hook(monkeypatch, allowed) == (0, "")
    assert run_hook(monkeypatch, blocked)[0] == 2


@pytest.mark.parametrize("tool", ["Read", "Grep", "Bash"])
def test_non_edit_tool_is_no_decision(monkeypatch, repo, tool):
    event = edit(repo / ".claude" / "worktrees" / "task" / "settings.json", tool)
    assert run_hook(monkeypatch, event) == (0, "")


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        '{"parts": ["hooks/"]}',
        '{"parts": {"hook": "hooks/"}}',
    ],
)
def test_broken_parts_file_does_not_block(monkeypatch, repo, content):
    parts_file(repo).write_text(content)
    assert run_hook(monkeypatch, edit(worktree(repo) / "settings.json")) == (0, "")


@pytest.mark.parametrize(
    "raw",
    [
        "{not json",
        "[]",
        '{"tool_name": "Edit"}',
        '{"tool_name": "Edit", "tool_input": {"file_path": 5}, "agent_id": "a1"}',
        '{"tool_name": "Edit", "tool_input": {"file_path": "x"}, "agent_id": 7}',
    ],
)
def test_broken_input_does_not_block(monkeypatch, repo, raw):
    assert run_hook(monkeypatch, raw) == (0, "")


def test_missing_git_does_not_block(monkeypatch, repo):
    def no_git(*_arguments, **_options):
        raise FileNotFoundError("git")

    monkeypatch.setattr(guard_parallel_parts.subprocess, "run", no_git)
    assert run_hook(monkeypatch, edit(worktree(repo) / "settings.json")) == (0, "")


@pytest.mark.parametrize("encoding", ["utf-8-sig", "utf-16"])
def test_registration_with_bom_is_read(monkeypatch, repo, encoding):
    registration(repo).write_text("hook\n", encoding=encoding)
    assert run_hook(monkeypatch, edit(worktree(repo) / "hooks/guard.py")) == (0, "")
    code, _reason = run_hook(monkeypatch, edit(worktree(repo) / "settings.json"))
    assert code == 2


def test_parts_file_with_bom_is_read(monkeypatch, repo):
    parts_file(repo).write_text(json.dumps(PARTS), encoding="utf-8-sig")
    code, _reason = run_hook(monkeypatch, edit(worktree(repo) / "settings.json"))
    assert code == 2


def test_relative_gitdir_pointer_finds_the_worktree(monkeypatch, repo):
    pointer = repo / ".git" / "worktrees" / f"agent-{AGENT}" / "gitdir"
    pointer.write_text("../../../.claude/worktrees/agent-a1/.git\n")
    assert run_hook(monkeypatch, edit(worktree(repo) / "hooks/guard.py")) == (0, "")


def test_missing_gitdir_pointer_does_not_block(monkeypatch, repo):
    (repo / ".git" / "worktrees" / f"agent-{AGENT}" / "gitdir").unlink()
    assert run_hook(monkeypatch, edit(worktree(repo) / "settings.json")) == (0, "")


def test_tool_input_that_is_not_an_object_does_not_block(monkeypatch, repo):
    event = {"tool_name": "Edit", "tool_input": "x", "agent_id": AGENT}
    assert run_hook(monkeypatch, event) == (0, "")


def test_common_dir_of_a_worktree_under_a_hebrew_folder(tmp_path, monkeypatch):
    """git prints the path as UTF-8; Windows would decode it with its codepage."""
    main = (tmp_path / "שולחן העבודה").resolve()
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    git(main, "commit", "-q", "--allow-empty", "-m", "init")
    worktree = main / ".claude" / "worktrees" / "task"
    git(main, "worktree", "add", "-q", str(worktree))
    real_run = subprocess.run

    def windows_run(*args, **kwargs):
        if kwargs.get("text") and "encoding" not in kwargs:
            kwargs["text"] = False
            result = real_run(*args, **kwargs)
            result.stdout = result.stdout.decode("cp1252", errors="replace")
            return result
        return real_run(*args, **kwargs)

    monkeypatch.setattr(guard_parallel_parts.subprocess, "run", windows_run)
    assert guard_parallel_parts.git_common_dir(worktree) == main / ".git"
