"""The setup script in reference/cloud.md, run as is against a local repo.

claude-config#132.

The block is taken from the doc, so the script Dolev pastes into the cloud environment
is the one tested. Only the REPO line changes, to a bare repo in a temp folder, and HOME
points at a temp folder, so the real ~/.claude is never touched.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DOC = ROOT / "skills" / "dev-setup" / "reference" / "cloud.md"
BLOCK = re.compile(r"<!-- setup-script:[^\n]*-->\n```bash\n(.*?)```", re.DOTALL)
TRACKED = (
    "CLAUDE.md",
    "rules/git.md",
    "skills/dev-next/SKILL.md",
    "hooks/block_force_push.py",
    "settings.json",
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def git(cwd: Path, *args: str) -> str:
    """Run git with no signing and a fixed author, whatever the machine's config."""
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


def setup_script(repo_url: str) -> str:
    match = BLOCK.search(DOC.read_text(encoding="utf-8"))
    assert match, "cloud.md has no setup-script block"
    script, count = re.subn(
        r"^REPO=.*$", f"REPO={repo_url}", match.group(1), flags=re.M
    )
    assert count == 1, "the block sets REPO exactly once"
    return script


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    """A bare repo with the real .gitignore and one file in each tracked folder."""
    work = tmp_path / "work"
    work.mkdir()
    git(work, "init", "-q")
    shutil.copy(ROOT / ".gitignore", work / ".gitignore")
    for name in TRACKED:
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_text(f"{name} v1\n", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "v1")
    bare = tmp_path / "remote.git"
    git(tmp_path, "clone", "-q", "--bare", str(work), str(bare))
    return bare


def claude_md(home: Path) -> str:
    return (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")


def run_setup(remote: Path, home: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(
        ["bash", "-c", setup_script(f"file://{remote.as_posix()}")],
        env=env,
        capture_output=True,
        text=True,
    )


def push_v2(remote: Path, tmp_path: Path) -> None:
    clone = tmp_path / "v2"
    git(tmp_path, "clone", "-q", str(remote), str(clone))
    (clone / "CLAUDE.md").write_text("CLAUDE.md v2\n", encoding="utf-8")
    git(clone, "commit", "-q", "-am", "v2")
    git(clone, "push", "-q", "origin", "main")


def test_creates_claude_folder_with_the_config(remote, tmp_path):
    home = tmp_path / "home"
    result = run_setup(remote, home)
    assert result.returncode == 0, result.stderr
    for name in TRACKED:
        assert (home / ".claude" / name).read_text(encoding="utf-8") == f"{name} v1\n"


def test_keeps_the_service_files_and_leaves_git_status_clean(remote, tmp_path):
    claude = tmp_path / "home" / ".claude"
    service = (
        "launcher-settings.json",
        "plugins/synced/manifest.json",
        "skills/synced/pdf/SKILL.md",
        "skills/session-start-hook/SKILL.md",
    )
    for name in service:
        (claude / name).parent.mkdir(parents=True, exist_ok=True)
        (claude / name).write_text("service\n", encoding="utf-8")

    result = run_setup(remote, tmp_path / "home")

    assert result.returncode == 0, result.stderr
    for name in service:
        assert (claude / name).read_text(encoding="utf-8") == "service\n"
    assert git(claude, "status", "--porcelain") == ""


def test_second_run_updates_to_the_new_main(remote, tmp_path):
    home = tmp_path / "home"
    assert run_setup(remote, home).returncode == 0
    push_v2(remote, tmp_path)

    result = run_setup(remote, home)

    assert result.returncode == 0, result.stderr
    assert claude_md(home) == "CLAUDE.md v2\n"


def test_unreachable_repo_warns_and_never_fails(tmp_path):
    result = run_setup(tmp_path / "missing.git", tmp_path / "home")

    assert result.returncode == 0
    assert "was not installed" in result.stderr


def test_installs_after_an_earlier_failed_run(remote, tmp_path):
    # A failed fetch leaves a .git with no commit next to the service files.
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "launcher-settings.json").write_text("service\n")
    assert run_setup(tmp_path / "missing.git", home).returncode == 0

    result = run_setup(remote, home)

    assert "was not installed" not in result.stderr
    assert claude_md(home) == "CLAUDE.md v1\n"


def test_stops_on_uncommitted_changes_and_keeps_them(remote, tmp_path):
    home = tmp_path / "home"
    assert run_setup(remote, home).returncode == 0
    edited = home / ".claude" / "rules" / "git.md"
    edited.write_text("edited in a session\n", encoding="utf-8")
    push_v2(remote, tmp_path)

    result = run_setup(remote, home)

    assert result.returncode == 0
    assert "uncommitted changes" in result.stderr
    assert edited.read_text(encoding="utf-8") == "edited in a session\n"
    assert claude_md(home) == "CLAUDE.md v1\n"
