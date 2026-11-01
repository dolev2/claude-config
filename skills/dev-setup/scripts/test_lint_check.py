"""lint_check.py: the lint settings a repo is missing, and copies that stray."""

import importlib.util
import shutil
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "lint_check.py"
spec = importlib.util.spec_from_file_location("lint_check", SCRIPT)
lint_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint_check)

WORKFLOW = lint_check.WORKFLOW
LINT_STEPS = "      - run: ruff check .\n      - run: npm --prefix frontend run lint\n"


def make_repo(root: Path, files: dict[str, str]) -> list[str]:
    """Write the files under root; return their paths as git ls-files lists them."""
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8", newline="")
    return list(files)


def copy_template(root: Path, template: str, to: str) -> str:
    (root / to).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(lint_check.TEMPLATES / template, root / to)
    return to


def test_no_code_needs_no_lint(tmp_path):
    files = make_repo(tmp_path, {"index.html": "<p></p>", "README.md": "# x"})
    assert lint_check.lint_gaps(tmp_path, files) == []


def test_python_without_settings(tmp_path):
    files = make_repo(tmp_path, {"app/main.py": "", WORKFLOW: "jobs: {}\n"})
    assert lint_check.lint_gaps(tmp_path, files) == [
        "missing ruff.toml",
        f"no ruff step in {WORKFLOW}",
    ]


def test_file_guide_copy_alone_needs_no_ruff(tmp_path):
    files = make_repo(
        tmp_path,
        {
            "index.html": "<p></p>",
            WORKFLOW: "      - run: python .github/file_guide_check.py\n",
        },
    ) + [copy_template(tmp_path, "file_guide_check.py", lint_check.FILE_GUIDE_CHECK)]
    assert lint_check.lint_gaps(tmp_path, files) == []
    assert lint_check.all_gaps(tmp_path, files) == []


def test_file_guide_copy_with_other_python_needs_ruff(tmp_path):
    files = make_repo(tmp_path, {"app/main.py": "", WORKFLOW: "jobs: {}\n"}) + [
        copy_template(tmp_path, "file_guide_check.py", lint_check.FILE_GUIDE_CHECK)
    ]
    assert lint_check.lint_gaps(tmp_path, files) == [
        "missing ruff.toml",
        f"no ruff step in {WORKFLOW}",
    ]


def test_python_without_a_workflow(tmp_path):
    files = make_repo(tmp_path, {"app/main.py": ""}) + [
        copy_template(tmp_path, "ruff.toml", "ruff.toml")
    ]
    assert lint_check.lint_gaps(tmp_path, files) == [f"missing {WORKFLOW}"]


def test_complete_setup_with_its_own_local_block(tmp_path):
    files = make_repo(
        tmp_path,
        {
            "app/main.py": "",
            "frontend/package.json": "{}",
            "frontend/src/App.jsx": "",
            WORKFLOW: LINT_STEPS,
        },
    )
    files += [
        copy_template(tmp_path, "ruff.toml", "ruff.toml"),
        copy_template(tmp_path, "eslint.config.js", "frontend/eslint.config.js"),
    ]
    with (tmp_path / "ruff.toml").open("a", encoding="utf-8") as f:
        f.write('target-version = "py313"\n')
    assert lint_check.lint_gaps(tmp_path, files) == []


def test_a_changed_rule_above_the_marker_differs(tmp_path):
    files = make_repo(tmp_path, {"app/main.py": "", WORKFLOW: LINT_STEPS}) + [
        copy_template(tmp_path, "ruff.toml", "ruff.toml")
    ]
    text = (tmp_path / "ruff.toml").read_text(encoding="utf-8")
    (tmp_path / "ruff.toml").write_text(
        text.replace("line-length = 88", "line-length = 100"), encoding="utf-8"
    )
    assert lint_check.lint_gaps(tmp_path, files) == ["differs ruff.toml"]


def test_a_copy_without_the_marker_differs(tmp_path):
    files = make_repo(
        tmp_path,
        {"app/main.py": "", "ruff.toml": "line-length = 88\n", WORKFLOW: LINT_STEPS},
    )
    assert lint_check.lint_gaps(tmp_path, files) == ["differs ruff.toml"]


def test_crlf_line_endings_are_not_a_difference(tmp_path):
    files = make_repo(tmp_path, {"app/main.py": "", WORKFLOW: LINT_STEPS})
    text = (lint_check.TEMPLATES / "ruff.toml").read_text(encoding="utf-8")
    files += make_repo(tmp_path, {"ruff.toml": text.replace("\n", "\r\n")})
    assert lint_check.lint_gaps(tmp_path, files) == []


def test_eslint_lives_next_to_the_nearest_package_json(tmp_path):
    files = make_repo(
        tmp_path,
        {
            "web/package.json": "{}",
            "web/src/pages/Home.jsx": "",
            WORKFLOW: "jobs: {}\n",
        },
    )
    files.append(copy_template(tmp_path, "eslint.config.js", "web/eslint.config.js"))
    (tmp_path / "web/eslint.config.js").write_text(
        (tmp_path / "web/eslint.config.js")
        .read_text(encoding="utf-8")
        .replace('"dist/", ', ""),
        encoding="utf-8",
    )
    assert lint_check.lint_gaps(tmp_path, files) == [
        "differs web/eslint.config.js",
        f"no lint step in {WORKFLOW}",
    ]


def test_jsx_without_a_package_json_looks_at_the_root(tmp_path):
    files = make_repo(tmp_path, {"src/App.jsx": "", WORKFLOW: LINT_STEPS})
    assert lint_check.lint_gaps(tmp_path, files) == ["missing eslint.config.js"]


GUIDE_STEP = "      - run: python .github/file_guide_check.py\n"


def test_file_guide_check_missing_everywhere(tmp_path):
    assert lint_check.file_guide_gaps(tmp_path) == [
        f"missing {lint_check.FILE_GUIDE_CHECK}",
        f"missing {WORKFLOW}",
    ]


def test_file_guide_check_with_its_own_exceptions_and_step(tmp_path):
    make_repo(tmp_path, {WORKFLOW: GUIDE_STEP})
    copy_template(tmp_path, "file_guide_check.py", lint_check.FILE_GUIDE_CHECK)
    copy = tmp_path / lint_check.FILE_GUIDE_CHECK
    text = copy.read_text(encoding="utf-8")
    copy.write_text(
        text.replace(
            "COVERED_BY_PATTERN: list[str] = []", 'COVERED_BY_PATTERN = ["*"]'
        ),
        encoding="utf-8",
    )
    assert lint_check.file_guide_gaps(tmp_path) == []


def test_file_guide_check_that_strays_and_has_no_step(tmp_path):
    make_repo(tmp_path, {WORKFLOW: LINT_STEPS})
    copy_template(tmp_path, "file_guide_check.py", lint_check.FILE_GUIDE_CHECK)
    copy = tmp_path / lint_check.FILE_GUIDE_CHECK
    copy.write_text("x = 1\n" + copy.read_text(encoding="utf-8"), encoding="utf-8")
    assert lint_check.file_guide_gaps(tmp_path) == [
        f"differs {lint_check.FILE_GUIDE_CHECK}",
        f"no file guide step in {WORKFLOW}",
    ]


def test_all_gaps_names_a_missing_workflow_once(tmp_path):
    files = make_repo(tmp_path, {"app/main.py": ""}) + [
        copy_template(tmp_path, "ruff.toml", "ruff.toml")
    ]
    assert lint_check.all_gaps(tmp_path, files) == [
        f"missing {WORKFLOW}",
        f"missing {lint_check.FILE_GUIDE_CHECK}",
    ]
