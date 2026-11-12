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


def test_a_deleted_folder_with_a_slash_is_gone():
    readme = guide("### השורש\n" + TABLE + "| `app.py` | x | y |\n| `old/` | x | y |")
    assert check(readme, ["app.py"]) == ([], ["old/"])


def test_two_sibling_folders_in_one_cell():
    readme = guide(
        "### השורש\n" + TABLE + "| `rules/`, `hooks/` | `a.md` ו-`b.py` | y |"
    )
    assert check(readme, ["rules/a.md", "hooks/b.py"]) == ([], [])


def test_a_code_block_inside_the_guide_is_no_heading():
    readme = guide(
        "### `app/`\n"
        + TABLE
        + "| `a.py` | x | y |\n\n```bash\n# install\n```\n\n| `b.py` | x | y |"
    )
    assert check(readme, ["app/a.py", "app/b.py"]) == ([], [])


def test_a_folder_row_name_covers_only_files_directly_in_it():
    readme = guide("### השורש\n" + TABLE + "| `src/` | `index` ו-`sub/App.jsx` | y |")
    files = ["src/index.js", "src/sub/App.jsx", "src/other/index.js"]
    assert check(readme, files) == (["src/other/index.js"], [])


def test_patterns_match_case_sensitively_everywhere():
    readme = guide("### השורש\n" + TABLE + "| `*.PY` | x | y |")
    assert check(readme, ["Readme.MD", "a.PY"], ["readme.md"]) == (["Readme.MD"], [])


def test_repo_files_keeps_hebrew_names(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "קובץ.md").write_text("", encoding="utf-8")
    assert file_guide_check.repo_files(tmp_path) == ["קובץ.md"]


def test_main_runs_in_a_repo_with_a_hebrew_path(tmp_path, monkeypatch):
    root = tmp_path / "שולחן העבודה"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    readme = guide("### השורש\n" + TABLE + "| `README.md` | x | y |")
    (root / "README.md").write_text(readme, encoding="utf-8")
    monkeypatch.chdir(root)
    assert file_guide_check.main([]) == 0


def test_a_path_in_two_rows_is_listed_twice():
    # What merge=union leaves when two branches edit the same row.
    readme = guide(
        "### השורש\n"
        + TABLE
        + "| `app.py` | x | y |\n| `db.py` | x | y |\n| `app.py` | x | z |"
    )
    assert file_guide_check.listed_twice(readme) == ["app.py"]


def test_the_same_name_in_two_folders_is_not_twice():
    readme = guide(
        "### `a/`\n" + TABLE + "| `x.py` | x | y |\n"
        "### `b/`\n" + TABLE + "| `x.py` | x | y |"
    )
    assert file_guide_check.listed_twice(readme) == []


def test_no_guide_lists_nothing_twice():
    assert file_guide_check.listed_twice("# repo\n") == []


# Several guides: a README per folder, and each file in the nearest one.


def guides(texts: dict[str, str], patterns: list[str] | None = None) -> dict[str, str]:
    return file_guide_check.find_guides(texts, patterns or [])


def problems(texts: dict[str, str], files: list[str], patterns=None) -> list[str]:
    found = guides(texts, patterns)
    result = file_guide_check.check_guides(found, files, patterns or [])
    return [message for _, message in result]


ROOT = guide("### השורש\n" + TABLE + "| `README.md` | x | y |")


def test_one_root_readme_gives_the_same_result_as_before():
    readme = guide("### השורש\n" + TABLE + "| `app.py` | x | y |\n| `old.py` | x | y |")
    assert problems({"README.md": readme}, ["README.md", "app.py", "db.py"]) == [
        "not in the guide: db.py (belongs in README.md)",
        "in README.md, but no such file: old.py",
    ]


def test_a_file_described_in_its_folder_readme_passes():
    hooks = guide("### ה-hooks\n" + TABLE + "| `guard.py` | x | y |")
    files = ["README.md", "hooks/README.md", "hooks/guard.py"]
    assert problems({"README.md": ROOT, "hooks/README.md": hooks}, files) == []


def test_a_file_missing_from_its_folder_readme_points_to_it():
    hooks = guide("### ה-hooks\n" + TABLE + "| `guard.py` | x | y |")
    files = ["README.md", "hooks/README.md", "hooks/guard.py", "hooks/new.py"]
    assert problems({"README.md": ROOT, "hooks/README.md": hooks}, files) == [
        "not in the guide: hooks/new.py (belongs in hooks/README.md)"
    ]


def test_a_file_the_root_describes_instead_of_its_folder_readme_fails():
    root = guide("### השורש\n" + TABLE + "| `hooks/guard.py` | x | y |")
    hooks = guide("### ה-hooks\n" + TABLE + "| `other.py` | x | y |")
    files = ["README.md", "hooks/README.md", "hooks/guard.py", "hooks/other.py"]
    assert problems({"README.md": root, "hooks/README.md": hooks}, files) == [
        "in hooks/README.md, but described in README.md: hooks/guard.py",
        "not in the guide: hooks/guard.py (belongs in hooks/README.md)",
    ]


def test_a_file_in_a_subfolder_without_a_readme_belongs_to_the_folder_above():
    setup = guide("### `scripts/`\n" + TABLE + "| `lint.py` | x | y |")
    files = ["README.md", "skills/setup/README.md", "skills/setup/scripts/lint.py"]
    assert problems({"README.md": ROOT, "skills/setup/README.md": setup}, files) == []


def test_a_readme_without_a_guide_section_is_a_plain_file():
    spec_format = "# the spec format\n\n| `S-1.1` | x |\n"
    root = guide("### השורש\n" + TABLE + "| `docs/specs/README.md` | x | y |")
    texts = {"README.md": root, "docs/specs/README.md": spec_format}
    assert list(guides(texts)) == ["README.md"]
    assert problems(texts, ["README.md", "docs/specs/README.md"]) == []


def test_a_readme_in_test_data_is_not_read():
    fixture = guide("### השורש\n" + TABLE + "| `greet.py` | x | y |")
    texts = {"README.md": ROOT, "evals/fixture/README.md": fixture}
    patterns = ["evals/fixture/*"]
    assert list(guides(texts, patterns)) == ["README.md"]
    files = ["README.md", "evals/fixture/README.md", "evals/fixture/greet.py"]
    assert problems(texts, files, patterns) == []


def test_a_name_twice_in_one_guide_fails_and_in_two_guides_is_described_elsewhere():
    hooks = guide("### ה-hooks\n" + TABLE + "| `a.py` | x | y |\n| `a.py` | x | z |")
    assert problems(
        {"README.md": ROOT, "hooks/README.md": hooks},
        ["README.md", "hooks/README.md", "hooks/a.py"],
    ) == ["in hooks/README.md twice: a.py"]
    root = guide("### `hooks/`\n" + TABLE + "| `a.py` | x | y |")
    hooks = guide("### ה-hooks\n" + TABLE + "| `a.py` | x | y |")
    assert problems(
        {"README.md": root, "hooks/README.md": hooks},
        ["README.md", "hooks/README.md", "hooks/a.py"],
    ) == ["in hooks/README.md, but described in README.md: hooks/a.py"]


def test_a_gone_file_names_its_readme():
    docs = guide("### השורש\n" + TABLE + "| `old.md` | x | y |")
    files = ["README.md", "docs/README.md"]
    assert problems({"README.md": ROOT, "docs/README.md": docs}, files) == [
        "in docs/README.md, but no such file: docs/old.md"
    ]


def test_without_a_root_guide_it_is_none():
    hooks = guide("### ה-hooks\n" + TABLE)
    found = guides({"hooks/README.md": hooks})
    assert file_guide_check.check_guides(found, ["hooks/README.md"], []) is None


def test_main_fails_on_a_file_its_folder_readme_misses(tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text(ROOT, encoding="utf-8")
    (tmp_path / "hooks").mkdir()
    hooks = guide("### ה-hooks\n" + TABLE + "| `guard.py` | x | y |")
    (tmp_path / "hooks" / "README.md").write_text(hooks, encoding="utf-8")
    (tmp_path / "hooks" / "guard.py").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert file_guide_check.main([]) == 0
    (tmp_path / "hooks" / "new.py").write_text("", encoding="utf-8")
    assert file_guide_check.main([]) == 1
    out = capsys.readouterr().out
    assert "not in the guide: hooks/new.py (belongs in hooks/README.md)" in out
    assert "file guide in hooks/README.md" in out
