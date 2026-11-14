import os
import subprocess
import sys
from pathlib import Path

import pytest
import size_check

SCRIPT = Path(__file__).with_name("size_check.py")


def lines(n: int) -> str:
    return "".join(f"x = {i}\n" for i in range(n))


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A git repo whose first commit is tagged `base`; the test commits HEAD on top."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write(repo: Path, files: dict[str, str | None]) -> None:
    for path, text in files.items():
        target = repo / path
        if text is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def commit(repo: Path, files: dict[str, str | None], tag: str | None = None) -> None:
    write(repo, files)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", "c")
    if tag:
        git(repo, "tag", tag)


def run(repo: Path, base: dict, head: dict) -> list[tuple]:
    commit(repo, base, tag="base")
    commit(repo, head)
    diff = size_check.git("diff", "--name-status", "-M", "-z", "base...HEAD").stdout
    return size_check.findings("base", size_check.changed_paths(diff))


def test_a_code_file_that_crosses_the_limit_warns(repo):
    found = run(repo, {"app.py": lines(300)}, {"app.py": lines(301)})
    assert found == [("app.py", 300, 301)]
    text = size_check.warning(*found[0])
    assert text.startswith("::warning file=app.py::")
    assert "300 שורות ← 301" in text
    assert "מי קורא ומתי" in text and "מתי לא מפצלים" in text


def test_a_new_file_over_the_limit_warns(repo):
    found = run(repo, {}, {"web/app.tsx": lines(301)})
    assert found == [("web/app.tsx", None, 301)]
    assert "קובץ חדש" in size_check.warning(*found[0])


@pytest.mark.parametrize(
    ("before", "after"),
    [(301, 400), (100, 300)],
    ids=["already-over", "exactly-the-limit"],
)
def test_no_warning_without_crossing(repo, before, after):
    assert run(repo, {"app.py": lines(before)}, {"app.py": lines(after)}) == []


@pytest.mark.parametrize(
    "path",
    [
        "test_app.py",
        "app_test.py",
        "web/app.test.tsx",
        "web/app.spec.ts",
        "backend/tests/helpers.py",
        "docs/specs/repo.md",
        "skills/dev-setup/reference/pipeline.md",
        "data/rows.json",
        "docs/page.html",
    ],
)
def test_skipped_files_never_warn(repo, path):
    assert run(repo, {}, {path: lines(400)}) == []


def test_a_skill_that_crosses_warns(repo):
    path = "skills/dev-code/SKILL.md"
    assert run(repo, {path: lines(250)}, {path: lines(320)}) == [(path, 250, 320)]


def test_a_deleted_file_does_not_warn_or_crash(repo):
    assert run(repo, {"app.py": lines(400), "keep.py": "x\n"}, {"app.py": None}) == []


def test_a_moved_file_already_over_the_limit_does_not_warn(repo):
    found = run(
        repo, {"old/app.py": lines(400)}, {"old/app.py": None, "new/app.py": lines(400)}
    )
    assert found == []


def test_a_path_with_a_space_and_a_colon_is_checked_and_escaped(repo):
    found = run(repo, {}, {"my app:v2.py": lines(301)})
    assert found == [("my app:v2.py", None, 301)]
    assert size_check.warning(*found[0]).startswith("::warning file=my app%3Av2.py::")


def test_the_run_exits_0_with_a_warning_and_writes_the_summary(repo, tmp_path_factory):
    commit(repo, {"app.py": lines(10)}, tag="base")
    commit(repo, {"app.py": lines(350)})
    summary = tmp_path_factory.mktemp("out") / "summary.md"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "base"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "GITHUB_STEP_SUMMARY": str(summary)},
    )
    assert result.returncode == 0
    assert result.stdout.startswith("::warning file=app.py::")
    assert "הקובץ `app.py`: 10 ← 350" in summary.read_text(encoding="utf-8")


def test_an_unknown_base_exits_non_zero_with_a_message(repo):
    commit(repo, {"app.py": "x\n"})
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "no-such-ref"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode != 0
    assert "no-such-ref" in result.stderr
