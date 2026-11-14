"""spec_repo_line.py: each chapter's "בריפו:" line names folders the repo has."""

import pytest
from spec_repo_line import check

FOLDERS = {"hooks", "skills", "skills/dev-setup"}


def is_dir(path: str) -> bool:
    """A repo with three folders and one file, hooks/run.py."""
    return path in FOLDERS


def spec(first_line: str) -> str:
    """A spec with one chapter whose first line is `first_line`."""
    return f"# Spec\n\n## פרק 1 · Hooks\n{first_line}\n\nWhat the chapter is.\n"


def test_valid_line_with_many_folders_has_no_findings():
    text = spec("**בריפו:** `hooks/`, `skills/`, `skills/dev-setup/`")
    assert check(text, is_dir) == ([], [])


@pytest.mark.parametrize(
    "path, reason",
    [
        ("gone/", "is no folder"),
        ("hooks/run.py", "is no folder"),
        ("/etc/", "absolute path"),
        ("C:/x/", "absolute path"),
        ("../other/", "leaves the repo"),
    ],
)
def test_bad_path_is_an_error_with_the_line_and_the_path(path, reason):
    errors, warnings = check(spec(f"**בריפו:** `hooks/`, `{path}`"), is_dir)
    assert warnings == []
    assert len(errors) == 1
    line, message = errors[0]
    assert line == 4
    assert reason in message and f"`{path}`" in message and "chapter 1" in message


@pytest.mark.parametrize(
    "first_line", ["**בריפו:**", "**בריפו:** hooks/", "**בריפו:** ``"]
)
def test_line_without_a_path_is_an_error(first_line):
    errors, _ = check(spec(first_line), is_dir)
    assert errors == [(4, errors[0][1])]
    assert "names no folder" in errors[0][1]


def test_chapter_without_the_line_warns():
    errors, warnings = check(spec("What the chapter is."), is_dir)
    assert errors == []
    assert warnings[0][0] == 3 and "no repo line" in warnings[0][1]


def test_line_that_is_not_first_under_the_heading_warns():
    text = "## פרק 2 · x\nWhat it is.\n**בריפו:** `hooks/`\n"
    errors, warnings = check(text, is_dir)
    assert errors == [] and len(warnings) == 1


def test_blank_lines_before_the_line_are_skipped():
    text = "## פרק 1 · x\n\n\n**בריפו:** `gone/`\n"
    errors, _ = check(text, is_dir)
    assert errors[0][0] == 4


@pytest.mark.parametrize(
    "text",
    [
        "# Spec\n\n## Stage one\n### S-1.1 · x\n",
        "```markdown\n## פרק 1 · example\n**בריפו:** `gone/`\n```\n",
        "",
    ],
)
def test_no_chapter_or_a_chapter_in_a_code_block_has_no_findings(text):
    assert check(text, is_dir) == ([], [])


def test_english_line_is_read():
    text = "## Chapter 1 · Hooks\n**In repo:** `gone/`\n"
    errors, warnings = check(text, is_dir)
    assert warnings == [] and "is no folder" in errors[0][1]


def test_each_chapter_is_checked():
    text = "## פרק 1 · a\n**בריפו:** `hooks/`\n\n## פרק 2 · b\nNo line.\n"
    errors, warnings = check(text, is_dir)
    assert errors == []
    assert [line for line, _ in warnings] == [4]
