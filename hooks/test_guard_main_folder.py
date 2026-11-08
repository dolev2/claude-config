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
shell_commands = sys.modules["shell_commands"]

GITIGNORE = """/*
!/.gitignore
!/CLAUDE.md
!/skills/
!/settings.json
!/.claude/
/.claude/*
!/.claude/CLAUDE.md
/skills/synced/
__pycache__/
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


@pytest.mark.parametrize(
    "relative",
    [
        ".git/config",
        ".git/hooks/pre-commit",
        ".GIT/config",
        "skills/x/__pycache__/helper.cpython-312.pyc",
        "skills/synced/y/SKILL.md",
        "skills/session-start-hook/SKILL.md",
        "agents/reviewer.md",
        "commands/ship.md",
        "plugins/p/plugin.json",
        "output-styles/short.md",
    ],
)
def test_live_ignored_file_in_main_folder_is_blocked(monkeypatch, root, relative):
    code, reason = run_hook(monkeypatch, edit(root / relative, "Write"))
    assert code == 2
    assert "worktree" in reason


def test_live_ignored_name_in_worktree_passes(monkeypatch, root):
    path = root / "worktrees" / "b" / "skills" / "x" / "__pycache__" / "a.pyc"
    assert run_hook(monkeypatch, edit(path, "Write")) == (0, "")


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
        "git reset --hard",
        "git reset --hard origin/main",
        "git reset --keep HEAD~1",
        "git restore .",
        "git restore --worktree --staged CLAUDE.md",
        "git stash",
        "git stash push -m x",
        "git stash pop",
        "git symbolic-ref HEAD refs/heads/x",
        "git symbolic-ref -d HEAD",
        "git --git-dir=/elsewhere/.git checkout feature",
        "git clean -fd",
        "git clean --force",
        "(git checkout feature)",
        "if true; then git checkout feature; fi",
        "env git checkout feature",
        "bash -c 'git stash'",
    ],
)
def test_branch_switch_in_main_folder_is_blocked(monkeypatch, root, command):
    code, reason = run_hook(monkeypatch, shell(command, root))
    assert code == 2
    assert "worktree" in reason


def test_cd_into_main_folder_is_followed(monkeypatch, root, tmp_path):
    command = f'cd "{root}" && git checkout feature'
    assert run_hook(monkeypatch, shell(command, tmp_path))[0] == 2


@pytest.mark.parametrize(
    "template",
    [
        "git --git-dir={root}/.git --work-tree={root} checkout feature",
        "git --git-dir {root}/.git checkout feature",
        "git --work-tree={root} reset --hard",
        "GIT_DIR={root}/.git git checkout feature",
        "GIT_WORK_TREE={root} git restore .",
        "env GIT_DIR={root}/.git git stash",
        "(cd {root} && git checkout feature)",
        "if cd {root}; then git checkout feature; fi",
        "export GIT_DIR={root}/.git; git checkout feature",
        "cd {root} && git status # look first\ngit checkout feature",
    ],
)
def test_other_ways_into_main_folder_are_blocked(monkeypatch, root, tmp_path, template):
    command = template.format(root=root)
    assert run_hook(monkeypatch, shell(command, tmp_path))[0] == 2


def test_dash_c_into_main_folder_is_blocked(monkeypatch, root, tmp_path):
    command = f'git -C "{root}" switch feature'
    assert run_hook(monkeypatch, shell(command, tmp_path, "PowerShell"))[0] == 2


def msys(path: Path) -> str:
    """The path as Git Bash writes it: C:\\Users\\x becomes /c/Users/x."""
    return f"/{path.drive[0].lower()}{path.as_posix()[2:]}"


@pytest.mark.skipif(sys.platform != "win32", reason="Git Bash paths exist on Windows")
@pytest.mark.parametrize(
    "template", ["cd {path}; git switch main", "git -C {path} checkout main"]
)
def test_git_bash_path_into_main_folder_is_blocked(
    monkeypatch, root, tmp_path, template
):
    command = template.format(path=msys(root))
    assert run_hook(monkeypatch, shell(command, tmp_path))[0] == 2


@pytest.mark.parametrize(
    ("text", "is_windows", "expected"),
    [
        ("/c/Users/x", True, "C:/Users/x"),
        ("/d", True, "D:"),
        ("/c/Users/x", False, "/c/Users/x"),
        ("/cc/x", True, "/cc/x"),
        ("skills/x", True, "skills/x"),
    ],
)
def test_native_path(text, is_windows, expected):
    assert shell_commands.native_path(text, is_windows) == expected


@pytest.mark.parametrize(
    "command",
    [
        "cat > notes.md <<'EOF'\ngit switch main\nEOF",
        'cat > notes.md << "EOF"\ngit checkout main\nEOF\necho done',
        "cat > notes.md <<-EOF\n\tgit switch main\n\tEOF",
    ],
)
def test_heredoc_body_is_not_a_command(monkeypatch, root, command):
    assert run_hook(monkeypatch, shell(command, root)) == (0, "")


def test_command_after_heredoc_is_checked(monkeypatch, root):
    command = "cat > notes.md <<'EOF'\ntext\nEOF\ngit switch main"
    assert run_hook(monkeypatch, shell(command, root))[0] == 2


@pytest.mark.parametrize(
    "command",
    [
        "git checkout feature",
        "git switch -c feature",
        "git reset --hard",
        "git stash",
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
    [
        "git pull",
        "git fetch origin",
        "git worktree add ../x",
        'echo "git checkout x"',
        "git reset",
        "git reset --soft HEAD~1",
        "git restore --staged CLAUDE.md",
        "git stash list",
        "git stash show -p",
        "git symbolic-ref HEAD",
        "git symbolic-ref --short HEAD",
        "git clean -n",
    ],
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
