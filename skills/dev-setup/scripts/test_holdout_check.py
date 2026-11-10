""".github/holdout_check.py: a skill and the held-out set never change in one diff."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / ".github" / "holdout_check.py"
spec = importlib.util.spec_from_file_location("holdout_check", SCRIPT)
holdout_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(holdout_check)


@pytest.mark.parametrize(
    ("files", "fails"),
    [
        (["skills/dev-ship/SKILL.md", "evals/holdout/x/prompt.md"], True),
        (
            ["skills/dev-setup/reference/pipeline.md", "evals/holdout/x/state.json"],
            True,
        ),
        (["skills/dev-ship/SKILL.md", "evals/cases/x/prompt.md"], False),
        (["evals/holdout/x/prompt.md", "evals/run.py"], False),
        (["skills/dev-setup/scripts/rank_issues.py", "evals/holdout/x/a.md"], False),
        ([], False),
    ],
)
def test_conflict(files, fails):
    skills, holdout = holdout_check.conflict(files)
    assert bool(skills and holdout) == fails


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A repo whose main has one commit, and a branch checked out on top of it."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "evals" / "holdout" / "a").mkdir(parents=True)
    (tmp_path / "evals" / "holdout" / "a" / "prompt.md").write_text("old")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    git(tmp_path, "checkout", "-q", "-b", "work")
    return tmp_path


def commit(repo, *paths):
    for path in paths:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text("x")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")


def run_script(repo):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "main"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_fails_on_both(repo):
    commit(repo, "skills/dev-ship/SKILL.md", "evals/holdout/a/prompt.md")
    result = run_script(repo)
    assert result.returncode == 1
    assert "evals/holdout/a/prompt.md" in result.stdout


def test_run_passes_on_a_skill_alone(repo):
    commit(repo, "skills/dev-ship/SKILL.md")
    assert run_script(repo).returncode == 0


def test_run_skips_the_pr_that_creates_the_set(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    commit(tmp_path, "README.md")
    git(tmp_path, "checkout", "-q", "-b", "work")
    commit(tmp_path, "skills/dev-ship/SKILL.md", "evals/holdout/a/prompt.md")
    result = run_script(tmp_path)
    assert result.returncode == 0
    assert "עוד לא קיים" in result.stdout
