"""scaffold.sh, through a case's setup.sh: the demo repo, its remote and the fake gh."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import run

pytestmark = [
    pytest.mark.skipif(not shutil.which("git"), reason="needs git"),
    # scaffold.sh runs the fake gh as a shebang script, inside the Linux-only evals.
    pytest.mark.skipif(sys.platform == "win32", reason="evals run on Linux"),
]


def setup_case(tmp_path: Path, name: str) -> tuple[Path, dict]:
    """Run a case's setup.sh as the eval does: in $HOME/cwd, the fake gh on PATH."""
    plugin = run.build_plugin(tmp_path / "work", holdout=False)
    fake_bin = run.install_fake_gh(tmp_path / "work")
    home = tmp_path / "home"
    workspace = home / "cwd"
    workspace.mkdir(parents=True)
    env = {
        "HOME": str(home),
        "PATH": os.pathsep.join(
            [str(fake_bin), str(Path(sys.executable).parent), os.environ["PATH"]]
        ),
    }
    script = plugin / "evals" / name / "setup.sh"
    subprocess.run(["bash", str(script)], cwd=workspace, env=env, check=True)
    return workspace, env


def test_merge_case_has_the_branch_and_its_open_pr(tmp_path):
    workspace, env = setup_case(tmp_path, "dev-ship-merge-on-request")
    assert (workspace / "gh-state" / "pulls" / "13.state").read_text() == "open\n"
    remote = Path(env["HOME"]) / "git" / "acme" / "demo.git"
    heads = subprocess.run(
        ["git", f"--git-dir={remote}", "branch", "--list"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "main" in heads
    assert "claude/issue-12" in heads
    view = subprocess.run(
        ["gh", "pr", "view", "13", "--json", "state", "--jq", ".state"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert (view.returncode, view.stdout) == (0, "OPEN\n")


def test_workspace_status_shows_only_the_repo(tmp_path):
    workspace, env = setup_case(tmp_path, "dev-code-ready-issue")
    (workspace / ".bashrc").write_text("")  # a placeholder the run mounts
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert status == ""


def test_demo_repo_can_add_a_worktree(tmp_path):
    # The eval sandbox makes a workspace's .git/worktrees and .git/config read-only,
    # so the demo repo keeps its git folder apart and .git is only a pointer (#372).
    workspace, env = setup_case(tmp_path, "dev-code-ready-issue")
    assert (workspace / ".git").is_file()
    added = subprocess.run(
        ["git", "worktree", "add", str(tmp_path / "wt"), "-b", "claude/issue-12-x"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert added.returncode == 0, added.stderr


@pytest.mark.parametrize(
    "name", ["dev-plan-gate-in-sprint", "dev-plan-gate-no-milestone"]
)
def test_gate_case_code_agrees_with_its_done_part(tmp_path, name):
    # The code on main already does what the Done part says, so #12 is not a bug and
    # the gate is the only right answer (#415).
    workspace, env = setup_case(tmp_path, name)
    greeting = subprocess.run(
        ["python3", "-c", "from greet import greet; print(greet(''))"],
        cwd=workspace,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert greeting == "Hello, stranger\n"
    spec = (workspace / "docs" / "specs" / "demo.md").read_text(encoding="utf-8")
    assert "**מצב:** Done (#11)" in spec
    assert "#12" not in spec


def grader_matches(workspace: Path, name: str) -> int:
    """How often a file grader of the web-task case matches its target file."""
    graders = run.EVALS / "cases" / "dev-code-web-task" / "graders"
    text = (graders / f"{name}.md").read_text(encoding="utf-8")
    target = re.search(r"path: ([^ }]+)", text).group(1)
    pattern = re.search(r"^pattern: '(.*)'$", text, re.MULTILINE).group(1)
    log = (workspace / target).read_text(encoding="utf-8")
    return len(re.findall(pattern.replace("''", "'"), log))


WORKTREE = "worktrees/demo-issue-12"
BRANCH = "claude/issue-12-home-page"
COMMIT = ["git", "commit", "-q", "--allow-empty", "-m", "עבודה"]


@pytest.mark.parametrize(
    ("steps", "matches"),
    [
        (
            [
                ("", ["git", "worktree", "add", WORKTREE, "-b", BRANCH]),
                (WORKTREE, COMMIT),
            ],
            0,
        ),
        ([("cwd", ["git", "checkout", "-q", "-b", BRANCH]), ("cwd", COMMIT)], 2),
        ([("cwd", COMMIT)], 1),
    ],
    ids=["worktree", "branch-in-main-folder", "commit-on-main"],
)
def test_worktree_grader_tells_the_main_folder_apart(tmp_path, steps, matches):
    # S-1.68: a commit in a worktree leaves the main folder's HEAD log alone, and any
    # switch or commit in the main folder after the case's setup shows up there.
    workspace, env = setup_case(tmp_path, "dev-code-web-task")
    home = Path(env["HOME"])
    for folder, command in steps:
        command = [str(home / c) if c == WORKTREE else c for c in command]
        cwd = home / folder if folder else workspace
        subprocess.run(command, cwd=cwd, env=env, check=True, capture_output=True)
    assert grader_matches(workspace, "work-in-worktree") == matches
