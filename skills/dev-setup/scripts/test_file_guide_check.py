"""templates/file_guide_check.py: what the guide misses, and what it names in vain."""

import importlib.util
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "templates" / "file_guide_check.py"
spec = importlib.util.spec_from_file_location("file_guide_check", SCRIPT)
file_guide_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(file_guide_check)

TABLE = "| קובץ | מה הוא | למה |\n|---|---|---|\n"


def guide(*sections: str) -> str:
    """A README whose file guide holds the given sections, and a section after it."""
    return "# repo\n\n## מדריך קבצים\n\n" + "\n".join(sections) + "\n## בדיקות\n"


def check(readme: str, files: list[str], patterns: list[str] | None = None):
    return file_guide_check.check(readme, files, patterns or [])


def test_a_path_is_relative_to_its_section_folder():
    readme = guide(
        "### `skills/dev-setup/`: הבית\n"
        + TABLE
        + "| `scripts/lint_check.py` | x | y |"
    )
    assert check(readme, ["skills/dev-setup/scripts/lint_check.py"]) == ([], [])


def test_a_name_in_a_description_is_not_a_row():
    readme = guide(
        "### השורש\n" + TABLE + "| `hooks/` | לפי `parallel-parts.json` | y |"
    )
    assert check(readme, ["hooks/guard.py"]) == (["hooks/guard.py"], [])


def test_prose_outside_the_tables_covers_nothing():
    readme = guide("`Sidebar.jsx` הוא התפריט.\n\n### השורש\n" + TABLE)
    assert check(readme, ["Sidebar.jsx"]) == (["Sidebar.jsx"], [])


def test_prose_outside_the_section_covers_nothing():
    readme = "# repo\n\n| `app.py` | x | y |\n" + guide("### השורש\n" + TABLE)
    assert check(readme, ["app.py"]) == (["app.py"], [])


def test_a_folder_row_covers_the_files_it_names_and_only_those():
    readme = guide(
        "### `frontend/src/`\n"
        + TABLE
        + "| `shell/` | `AppShell` ו-`Sidebar.jsx` ו-`menu/Item.jsx` | y |"
    )
    files = [
        "frontend/src/shell/AppShell.jsx",
        "frontend/src/shell/Sidebar.jsx",
        "frontend/src/shell/menu/Item.jsx",
        "frontend/src/shell/New.jsx",
    ]
    assert check(readme, files) == (["frontend/src/shell/New.jsx"], [])


def test_a_bare_name_sits_in_the_folder_of_the_name_before_it():
    readme = guide(
        "### השורש\n" + TABLE + "| `.github/workflows/gate.yml`, `sync.yml` | x | y |"
    )
    files = [".github/workflows/gate.yml", ".github/workflows/sync.yml", "sync.yml"]
    assert check(readme, files) == (["sync.yml"], [])


def test_a_pattern_covers_and_a_pattern_that_matches_nothing_is_gone():
    readme = guide(
        "### `hooks/`\n" + TABLE + "| `test_*.py` | x | y |\n| `*.ps1` | x | y |"
    )
    assert check(readme, ["hooks/test_a.py"]) == ([], ["hooks/*.ps1"])


def test_a_row_for_a_deleted_file_is_gone():
    readme = guide("### השורש\n" + TABLE + "| `app.py` | x | y |\n| `old.py` | x | y |")
    assert check(readme, ["app.py"]) == ([], ["old.py"])


def test_a_folder_row_exists_while_a_file_sits_in_it():
    readme = guide(
        "### `skills/`\n" + TABLE + "| `dev-plan` | x | y |\n| `dev-gone` | x | y |"
    )
    assert check(readme, ["skills/dev-plan/SKILL.md"], ["skills/*/SKILL.md"]) == (
        [],
        ["skills/dev-gone"],
    )


def test_a_local_pattern_covers():
    readme = guide("### השורש\n" + TABLE)
    assert check(readme, ["backend/tests/test_x.py"], ["backend/tests/test_*.py"]) == (
        [],
        [],
    )


def test_the_english_heading_counts_and_a_missing_one_is_none():
    readme = "# repo\n\n## File guide\n\n" + TABLE + "| `app.py` | x | y |\n"
    assert check(readme, ["app.py"]) == ([], [])
    assert check("# repo\n\nSee the מדריך קבצים below.\n", ["app.py"]) is None


def test_sub_headings_stay_inside_the_guide():
    readme = guide("### השורש\n" + TABLE + "| `a.py` | x | y |\n#### עוד\n| `b.py` |")
    assert check(readme, ["a.py", "b.py"]) == ([], [])


def test_repo_files_sees_new_files_and_skips_ignored_ones(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("", encoding="utf-8")
    (tmp_path / "run.log").write_text("", encoding="utf-8")
    assert sorted(file_guide_check.repo_files(tmp_path)) == [".gitignore", "new.py"]
