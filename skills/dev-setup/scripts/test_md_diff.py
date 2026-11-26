"""Tests for md_diff.py: the `diff` blocks of Markdown files in the chat (S-1.65)."""

import subprocess
import sys
from pathlib import Path

import md_diff
import pytest

SCRIPT = Path(__file__).with_name("md_diff.py")
PR_URL = "https://github.com/o/r/pull/7/files"


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repo with a `base` branch, and the working tree on `head` off it."""
    run_git(tmp_path, "init", "-q", "-b", "base")
    run_git(tmp_path, "config", "user.email", "t@example.com")
    run_git(tmp_path, "config", "user.name", "t")
    (tmp_path / "doc.md").write_text(
        "שורה אחת\nשורה שתיים\nשורה שלוש\n", encoding="utf-8"
    )
    (tmp_path / "old name.md").write_text(
        "".join(f"line {i}\n" for i in range(20)), encoding="utf-8"
    )
    (tmp_path / "gone.md").write_text("ייעלם\n", encoding="utf-8")
    (tmp_path / "code.py").write_text("x = 1\n", encoding="utf-8")
    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-q", "-m", "base")
    run_git(tmp_path, "checkout", "-q", "-b", "head")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def commit(repo: Path) -> None:
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-q", "-m", "change")


def output(*extra: str) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "base", "--pr-url", PR_URL, *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_changed_file_gets_a_block_with_its_name(repo: Path) -> None:
    (repo / "doc.md").write_text("שורה אחת\nשורה חדשה\nשורה שלוש\n", encoding="utf-8")
    commit(repo)
    text = output()
    assert "הקובץ `doc.md`" in text
    assert "```diff" in text
    assert "-שורה שתיים" in text and "+שורה חדשה" in text
    assert " שורה אחת" in text  # a context line around the change
    assert "diff --git" not in text and "index " not in text


def test_new_deleted_and_renamed_files(repo: Path) -> None:
    (repo / "new.md").write_text("חדש\n", encoding="utf-8")
    (repo / "gone.md").unlink()
    run_git(repo, "mv", "old name.md", "new name.md")
    lines = (
        (repo / "new name.md")
        .read_text(encoding="utf-8")
        .replace("line 3\n", "line three\n")
    )
    (repo / "new name.md").write_text(lines, encoding="utf-8")
    commit(repo)
    text = output()
    assert "קובץ חדש: `new.md`" in text and "+חדש" in text
    assert "קובץ שנמחק: `gone.md`" in text and "-ייעלם" in text
    assert "שם שונה: `old name.md` ← `new name.md`" in text
    assert "+line three" in text
    assert "+line 19" not in text  # only the changed lines of a renamed file


def test_only_code_prints_nothing(repo: Path) -> None:
    (repo / "code.py").write_text("x = 2\n", encoding="utf-8")
    commit(repo)
    assert output() == ""


@pytest.mark.parametrize(
    ("sizes", "cut", "skipped"),
    [
        ([150], None, []),
        ([151], "a.md", []),
        ([100, 100, 10], "b.md", ["c.md"]),
    ],
)
def test_the_limit(sizes: list[int], cut: str | None, skipped: list[str]) -> None:
    patches = [
        (md_diff.Change("A", name, name), [f"+{i}" for i in range(size)])
        for name, size in zip(["a.md", "b.md", "c.md"], sizes, strict=False)
    ]
    text = md_diff.render(patches, PR_URL)
    shown = [line for line in text.splitlines() if line.startswith("+")]
    assert len(shown) == min(sum(sizes), 150)
    if cut is None:
        assert "נחתך" not in text
        return
    assert "ה-diff נחתך ב-150 שורות." in text
    assert f"הקובץ `{cut}` הוצג בחלקו." in text
    for name in skipped:
        assert f"`{name}`" in text.split("לא הוצגו:")[1]
    assert PR_URL in text


def test_unknown_ref_says_so_and_exits_zero(repo: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "nope", "--pr-url", PR_URL],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert "ה-diff של קובצי ה-MD לא נקרא." in result.stdout
    assert PR_URL in result.stdout


def test_missing_base_is_exit_two() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True
    )
    assert result.returncode == 2


def test_fence_is_longer_than_backticks_inside(repo: Path) -> None:
    (repo / "doc.md").write_text(
        "שורה אחת\n```bash\nls\n```\nשורה שלוש\n", encoding="utf-8"
    )
    commit(repo)
    text = output()
    assert "````diff" in text
    assert text.rstrip().endswith("````")


def test_files_without_hunks_still_get_their_heading(repo: Path) -> None:
    run_git(repo, "mv", "gone.md", "moved.md")
    (repo / "empty.md").write_text("", encoding="utf-8")
    commit(repo)
    text = output()
    assert "שם שונה: `gone.md` ← `moved.md`" in text
    assert "קובץ חדש: `empty.md`" in text
    assert "```diff" not in text


@pytest.mark.skipif(sys.platform == "win32", reason="Windows forbids * in a file name")
def test_a_star_in_a_name_is_not_a_glob(repo: Path) -> None:
    (repo / "a*.md").write_text("כוכבית\n", encoding="utf-8")
    (repo / "abc.md").write_text("שכן\n", encoding="utf-8")
    commit(repo)
    text = output()
    star_block = text.split("קובץ חדש: `a*.md`")[1].split("קובץ חדש:")[0]
    assert "+כוכבית" in star_block and "+שכן" not in star_block


def test_bytes_that_are_not_utf8_do_not_crash(repo: Path) -> None:
    (repo / "doc.md").write_bytes(b"\xff\xfe broken\n")
    commit(repo)
    assert "הקובץ `doc.md`" in output()
