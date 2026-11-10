"""scaffold.sh, through a case's setup.sh: the demo repo, its remote and the fake gh."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import run

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="needs git")


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
