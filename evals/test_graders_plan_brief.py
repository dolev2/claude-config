"""The graders of "בקצרה" in dev-plan-explore-issue, run on sample bodies, no model.

A missing section fails only summary-present; a line that breaks the rule fails only
the grader of its kind, so the report tells the two apart (S-1.67).
"""

import re
from pathlib import Path

import pytest
from graders import regex_pattern

GRADERS = Path(__file__).parent / "cases" / "dev-plan-explore-issue" / "graders"
BRIEF = (
    "summary-present",
    "summary-no-file-names",
    "summary-no-function-names",
    "summary-no-code",
)


def pattern_of(name: str) -> re.Pattern:
    """The grader's regex, read from the single-quoted `pattern:` line of its file."""
    return re.compile(regex_pattern(GRADERS / f"{name}.md"))


def failing(body: str) -> set[str]:
    """The brief graders that fail on this body: their pattern is not found in it."""
    return {name for name in BRIEF if not pattern_of(name).search(body)}


def body_with(brief_lines: list[str] | None) -> str:
    """An issue body whose Plan has these "בקצרה" lines, or no "בקצרה" at all."""
    brief = (
        "#### בקצרה\n" + "".join(f"{line}\n" for line in brief_lines) + "\n"
        if brief_lines is not None
        else ""
    )
    return (
        "### מה רוצים\n\nטקסט.\n\n### Plan\n\n"
        "**Branch:** `claude/issue-12-empty-name`\n\n"
        f"{brief}#### פירוט טכני\n\n##### הגישה\n- `greet` ב-`greet.py`.\n\n"
        "### שאלות פתוחות\n\n_אין._\n"
    )


GOOD = [
    "- **אפיון:** `docs/specs/demo.md` S-1.1 · ברכה לפי שם",
    '- **איפה באפיון:** החלק יושב בפרק 1, "ברכות".\\',
    'היום מי שלא נתן שם מקבל "Hello, " קטוע.',
    "- **החלטות שמחכות לדולב:** אין",
]


def test_a_plan_that_keeps_the_rule_passes_every_grader():
    assert failing(body_with(GOOD)) == set()


def test_the_spec_line_may_name_the_file_with_the_colon_outside_the_bold():
    lines = ["- **אפיון**: docs/specs/demo.md S-1.1", *GOOD[1:]]
    assert failing(body_with(lines)) == set()


def test_a_missing_section_fails_only_the_presence_grader():
    assert failing(body_with(None)) == {"summary-present"}


@pytest.mark.parametrize(
    ("line", "grader"),
    [
        ("- **הבעיה:** הבדיקה ב-test_home.py נכשלת.", "summary-no-file-names"),
        ("- **איפה באפיון:** כתוב ב-docs/specs/demo.md.", "summary-no-file-names"),
        ("- **הבעיה:** הפונקציה greet מחזירה ברכה קטועה.", "summary-no-function-names"),
        ('- **מה ישתנה:** הברכה תהיה `"Hello, stranger"`.', "summary-no-code"),
    ],
)
def test_a_line_that_breaks_the_rule_fails_only_its_kind(line, grader):
    assert failing(body_with([*GOOD, line])) == {grader}


def test_a_file_name_that_is_also_the_function_fails_both_kinds():
    line = "- **הבעיה:** greet.py שובר את הברכה."
    assert failing(body_with([*GOOD, line])) == {
        "summary-no-file-names",
        "summary-no-function-names",
    }


def test_an_empty_section_passes():
    assert failing(body_with([])) == set()


def test_a_section_at_the_end_of_the_body_is_checked_by_its_lines():
    body = "### Plan\n\n#### בקצרה\n" + "\n".join(GOOD)
    assert failing(body) == set()
    assert failing(f"{body}\n- **הבעיה:** greet שבורה.") == {
        "summary-no-function-names"
    }


def test_a_bold_spec_word_with_no_colon_is_an_ordinary_line():
    line = "- **אפיון** greet.py"
    assert failing(body_with([line, *GOOD[1:]])) == {
        "summary-no-file-names",
        "summary-no-function-names",
    }


@pytest.mark.parametrize("name", BRIEF)
def test_the_message_says_where_the_line_is(name):
    """The rule the report prints: the section is missing, or where the line is."""
    text = (GRADERS / f"{name}.md").read_text(encoding="utf-8")
    rule = [line for line in text.split("---", 2)[2].splitlines() if line.strip()][0]
    if name == "summary-present":
        assert "חסר" in rule
    else:
        assert "gh-state/issues/12.body.md" in rule
