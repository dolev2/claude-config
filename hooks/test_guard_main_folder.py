"""guard_main_folder.py: repo edits and branch switches in the main folder are blocked.

Each test builds a small main folder: a git repo with a .gitignore like the real one,
and two worktrees, one under .claude/worktrees/ and one under worktrees/.
"""

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "guard_main_folder.py"
spec = importlib.util.spec_from_file_location("guard_main_folder", SCRIPT)
guard_main_folder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard_main_folder)

GITIGNORE = """/*
!/.gitignore
!/CLAUDE.md
!/skills/
!/settings.json
!/.claude/
/.claude/*
!/.claude/CLAUDE.md
"""


class FakeStream:
    """A stdin or stderr stand-in with the `.buffer` the hook reads and writes."""

    def __init__(self, data: bytes = b"") -> None:
        self.buffer = io.BytesIO(data)

    def flush(self) -> None:
        pass


def git(folder: Path, *arguments: str) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(folder),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            *arguments,
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def root(tmp_path, monkeypatch) -> Path:
    """A main folder with tracked files, ignored files and two worktrees."""
    main = (tmp_path / "config").resolve()
    main.mkdir()
    (main / ".gitignore").write_text(GITIGNORE)
    (main / "CLAUDE.md").write_text("rules\n")
    (main / "settings.json").write_text("{}\n")
    (main / "skills" / "x").mkdir(parents=True)
    (main / "skills" / "x" / "SKILL.md").write_text("skill\n")
    git(main, "init", "-q", "-b", "main")
    git(main, "add", ".")
    git(main, "commit", "-q", "-m", "init")
    git(main, "worktree", "add", "-q", str(main / ".claude" / "worktrees" / "a"))
    git(main, "worktree", "add", "-q", str(main / "worktrees" / "b"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(main))
    return main


def run_hook(monkeypatch, event: dict) -> tuple[int, str]:
    """Run main() on the event as stdin; return the exit code and stderr."""
    stderr = FakeStream()
    monkeypatch.setattr(sys, "stdin", FakeStream(json.dumps(event).encode("utf-8")))
    monkeypatch.setattr(sys, "stderr", stderr)
    code = guard_main_folder.main()
    return code, stderr.buffer.getvalue().decode("utf-8")


def edit(path: Path, tool: str = "Edit") -> dict:
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"tool_name": tool, "tool_input": {key: str(path)}, "cwd": str(path.parent)}


def shell(command: str, cwd: Path, tool: str = "Bash") -> dict:
    return {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(cwd)}


@pytest.mark.parametrize(
    ("relative", "tool"),
    [
        ("CLAUDE.md", "Edit"),
        ("skills/x/SKILL.md", "Write"),
        ("skills/new/folder/SKILL.md", "Write"),
        (".claude/CLAUDE.md", "MultiEdit"),
        ("skills/x/notes.ipynb", "NotebookEdit"),
    ],
)
def test_repo_file_in_main_folder_is_blocked(monkeypatch, root, relative, tool):
    code, reason = run_hook(monkeypatch, edit(root / relative, tool))
    assert code == 2
    assert "worktree" in reason


@pytest.mark.parametrize("worktree", [".claude/worktrees/a", "worktrees/b"])
@pytest.mark.parametrize("relative", ["CLAUDE.md", "skills/x/SKILL.md"])
def test_same_file_in_worktree_passes(monkeypatch, root, worktree, relative):
    assert run_hook(monkeypatch, edit(root / worktree / relative)) == (0, "")


@pytest.mark.parametrize(
    "relative",
    [
        "projects/p/memory/MEMORY.md",
        "projects/p/memory/new-fact.md",
        "plans/plan.md",
        ".claude/settings.local.json",
        "settings.json",
        "worktrees/stray.md",
    ],
)
def test_files_outside_the_repo_and_settings_pass(monkeypatch, root, relative):
    assert run_hook(monkeypatch, edit(root / relative, "Write")) == (0, "")


def test_path_outside_main_folder_passes_without_git(monkeypatch, root, tmp_path):
    def no_git(*_arguments):
        raise AssertionError("git should not run for a path outside the main folder")

    monkeypatch.setattr(guard_main_folder, "run_git", no_git)
    assert run_hook(monkeypatch, edit(tmp_path / "other" / "CLAUDE.md")) == (0, "")


@pytest.mark.parametrize(
    "command",
    [
        "git checkout feature",
        "git switch -c feature",
        "git checkout -- CLAUDE.md",
        "git status && git checkout main",
        "cd skills && git switch feature",
    ],
)
def test_branch_switch_in_main_folder_is_blocked(monkeypatch, root, command):
    code, reason = run_hook(monkeypatch, shell(command, root))
    assert code == 2
    assert "worktree" in reason


def test_cd_into_main_folder_is_followed(monkeypatch, root, tmp_path):
    command = f'cd "{root}" && git checkout feature'
    assert run_hook(monkeypatch, shell(command, tmp_path))[0] == 2


def test_dash_c_into_main_folder_is_blocked(monkeypatch, root, tmp_path):
    command = f'git -C "{root}" switch feature'
    assert run_hook(monkeypatch, shell(command, tmp_path, "PowerShell"))[0] == 2


@pytest.mark.parametrize(
    "command",
    [
        "git checkout feature",
        "git switch -c feature",
    ],
)
def test_branch_switch_in_worktree_passes(monkeypatch, root, command):
    worktree = root / ".claude" / "worktrees" / "a"
    assert run_hook(monkeypatch, shell(command, worktree)) == (0, "")


def test_dash_c_into_worktree_passes(monkeypatch, root):
    command = "git -C worktrees/b checkout feature"
    assert run_hook(monkeypatch, shell(command, root)) == (0, "")


@pytest.mark.parametrize(
    "command",
    ["git pull", "git fetch origin", "git worktree add ../x", 'echo "git checkout x"'],
)
def test_other_git_commands_in_main_folder_pass(monkeypatch, root, command):
    assert run_hook(monkeypatch, shell(command, root)) == (0, "")


def test_missing_git_lets_the_edit_through(monkeypatch, root):
    monkeypatch.setattr(guard_main_folder, "run_git", lambda *_arguments: None)
    assert run_hook(monkeypatch, edit(root / "CLAUDE.md")) == (0, "")


@pytest.mark.parametrize("raw", ["", "not json", "[]", '{"tool_name": "Edit"}'])
def test_unreadable_input_passes(monkeypatch, raw):
    monkeypatch.setattr(sys, "stdin", FakeStream(raw.encode("utf-8")))
    assert guard_main_folder.main() == 0
