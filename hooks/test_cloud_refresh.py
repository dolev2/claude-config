"""cloud_refresh.py: a cloud session's ~/.claude moves to the latest main, safely."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "cloud_refresh.py"
spec = importlib.util.spec_from_file_location("cloud_refresh", SCRIPT)
cloud_refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cloud_refresh)


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
    ).stdout


def commit(work: Path, text: str) -> None:
    (work / "CLAUDE.md").write_text(text, encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", text.strip())
    git(work, "push", "-q", "origin", "main")


@pytest.fixture
def setup(tmp_path: Path):
    """A remote named like claude-config, a clone at HOME/.claude, and a work clone."""
    remote = tmp_path / "dolev2" / "claude-config.git"
    remote.parent.mkdir()
    git(tmp_path, "init", "-q", "--bare", str(remote))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(remote), str(work))
    commit(work, "v1\n")
    home = tmp_path / "home"
    home.mkdir()
    git(home, "clone", "-q", str(remote), ".claude")
    return home, work


def claude_md(home: Path) -> str:
    return (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")


def run_main(
    monkeypatch, home: Path, remote: str | None = "true", argv: list[str] = ()
) -> int:
    monkeypatch.setattr(Path, "home", lambda: home)
    if remote is None:
        monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    else:
        monkeypatch.setenv("CLAUDE_CODE_REMOTE", remote)
    return cloud_refresh.main(list(argv))


def test_cloud_session_moves_to_the_new_main(monkeypatch, setup):
    home, work = setup
    commit(work, "v2\n")

    run_main(monkeypatch, home)

    assert claude_md(home) == "v2\n"


def test_desktop_session_is_left_alone(monkeypatch, setup):
    home, work = setup
    commit(work, "v2\n")

    run_main(monkeypatch, home, remote=None)

    assert claude_md(home) == "v1\n"


def test_uncommitted_changes_are_kept(monkeypatch, setup):
    home, work = setup
    commit(work, "v2\n")
    (home / ".claude" / "CLAUDE.md").write_text("edited\n", encoding="utf-8")

    run_main(monkeypatch, home)

    assert claude_md(home) == "edited\n"


def test_other_repo_is_left_alone(monkeypatch, setup):
    home, work = setup
    commit(work, "v2\n")
    git(home / ".claude", "remote", "set-url", "origin", "https://example.com/x.git")

    run_main(monkeypatch, home)

    assert claude_md(home) == "v1\n"


def test_unreachable_remote_does_not_raise(monkeypatch, setup, tmp_path):
    home, _ = setup
    git(
        home / ".claude",
        "remote",
        "set-url",
        "origin",
        str(tmp_path / "dolev2" / "claude-config-missing.git"),
    )

    run_main(monkeypatch, home)

    assert claude_md(home) == "v1\n"


def test_no_claude_folder_does_not_raise(monkeypatch, tmp_path):
    run_main(monkeypatch, tmp_path / "empty-home")


def test_the_hook_prints_nothing(monkeypatch, setup, capsys):
    home, work = setup
    commit(work, "v2\n")

    assert run_main(monkeypatch, home) == 0

    assert capsys.readouterr().out == ""


def test_report_after_a_refresh(monkeypatch, setup, capsys):
    home, work = setup
    commit(work, "v2\n")
    new_main = git(work, "rev-parse", "HEAD").strip()

    assert run_main(monkeypatch, home, argv=["--report"]) == 0

    assert capsys.readouterr().out == f"refreshed {new_main}\n"
    assert claude_md(home) == "v2\n"


def test_report_with_uncommitted_changes(monkeypatch, setup, capsys):
    home, work = setup
    commit(work, "v2\n")
    (home / ".claude" / "CLAUDE.md").write_text("edited\n", encoding="utf-8")

    assert run_main(monkeypatch, home, argv=["--report"]) == 1

    assert capsys.readouterr().out == "not refreshed: uncommitted changes\n"
    assert claude_md(home) == "edited\n"


def test_report_with_an_unreachable_remote(monkeypatch, setup, tmp_path, capsys):
    home, _ = setup
    missing = tmp_path / "dolev2" / "claude-config-missing.git"
    git(home / ".claude", "remote", "set-url", "origin", str(missing))

    assert run_main(monkeypatch, home, argv=["--report"]) == 1

    assert capsys.readouterr().out == "not refreshed: fetch failed\n"


def test_report_outside_a_cloud_session(monkeypatch, setup, capsys):
    home, work = setup
    commit(work, "v2\n")

    assert run_main(monkeypatch, home, remote=None, argv=["--report"]) == 1

    assert capsys.readouterr().out == "not refreshed: not a cloud session\n"
    assert claude_md(home) == "v1\n"


def test_report_from_the_command_line(setup, tmp_path):
    home, work = setup
    commit(work, "v2\n")
    (home / ".claude" / "CLAUDE.md").write_text("edited\n", encoding="utf-8")
    env = {**os.environ, "HOME": str(home), "CLAUDE_CODE_REMOTE": "true"}

    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--report"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert run.returncode == 1
    assert run.stdout == "not refreshed: uncommitted changes\n"
