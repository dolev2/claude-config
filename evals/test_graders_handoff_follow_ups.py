"""The follow-up graders of dev-code-ready-issue, run on sample hand-offs, no model.

One grader checks the heading is there, the other what its first item opens with.
A missing heading fails only the first, so the report says which one broke (S-1.72).
"""

import re
from pathlib import Path

import pytest
from graders import regex_pattern

GRADERS = Path(__file__).parent / "cases" / "dev-code-ready-issue" / "graders"
STRUCTURE = "handoff-follow-ups"
CONTENT = "handoff-follow-ups-type"


def failing(comments: str) -> set[str]:
    """The follow-up graders whose pattern is not found in these comments."""
    return {
        name
        for name in (STRUCTURE, CONTENT)
        if not re.search(regex_pattern(GRADERS / f"{name}.md"), comments)
    }


def handoff(follow_ups: str | None) -> str:
    """A hand-off comment with this "משימות המשך" section, or with no such heading."""
    section = f"#### משימות המשך\n{follow_ups}\n\n" if follow_ups is not None else ""
    return (
        "**השורה התחתונה:**\\\nה-PR מוכן לסקירה.\n\n"
        "סקירת קוד: ממצא אחד, תוקן.\n\n"
        f"{section}"
        'המיזוג: דולב כותב "תמזג את #12".\n'
    )


@pytest.mark.parametrize(
    "first_item",
    [
        "אין משימות המשך.",
        "- אין משימות המשך",
        "1. **מוצר:** ברכה בשפה של המשתמש.",
        "- _תהליך:_ כלל חדש בנוהל.",
        "תהליך: כלל חדש בנוהל.",
    ],
)
def test_a_good_section_passes_both(first_item):
    assert failing(handoff(first_item)) == set()


@pytest.mark.parametrize(
    "comments",
    [
        handoff(None),
        handoff(None).replace("סקירת קוד", "#### משימות המשך: סקירת קוד"),
        handoff(None) + "ראו #### משימות המשך בהערה הקודמת.\n",
    ],
    ids=["no heading", "heading with text after it", "heading mid-line"],
)
def test_a_missing_heading_fails_only_the_structure_grader(comments):
    assert failing(comments) == {STRUCTURE}


@pytest.mark.parametrize(
    "first_item",
    ["- ברכה בשפה של המשתמש.", "1. **רעיון:** ברכה בשפה של המשתמש.", ""],
)
def test_a_first_item_with_no_kind_fails_only_the_content_grader(first_item):
    assert failing(handoff(first_item)) == {CONTENT}


def test_each_message_says_one_thing():
    """The structure message says what is missing; the content one, what broke."""

    def rule(name: str) -> str:
        text = (GRADERS / f"{name}.md").read_text(encoding="utf-8")
        return [line for line in text.split("---", 2)[2].splitlines() if line.strip()][
            0
        ]

    assert "חסרה" in rule(STRUCTURE)
    assert "סוג" not in rule(STRUCTURE)
    assert "לא מתחיל בסוג" in rule(CONTENT)
    assert "חסר" not in rule(CONTENT)
