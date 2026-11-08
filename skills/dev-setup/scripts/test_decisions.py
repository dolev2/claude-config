"""docs/decisions/: every decision page is whole, and every pointer to one is live.

A decision page (claude-config#187) holds one decision that crosses tasks: a status
line, then four parts. A page is never edited; a new page replaces it, and the old
page's status line names the new one. The rules point at the pages, so a pointer to a
page that is gone would send a session nowhere.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
DECISIONS = ROOT / "docs" / "decisions"
PAGES = sorted(DECISIONS.glob("*.md"))
TEMPLATE = ROOT / "skills" / "dev-setup" / "templates" / "decision.md"
PARTS = ("רקע", "החלטה", "חלופות שנדחו", "מחיר")
STATUS = re.compile(
    r"^\*\*מצב:\*\* (בתוקף|הוחלף ב-\[([\w-]+\.md)\]\(\2\))", re.MULTILINE
)
REPLACES = re.compile(r"^\*\*מחליף:\*\* \[([\w-]+\.md)\]\(\1\)", re.MULTILINE)
POINTER = re.compile(r"docs/decisions/([\w-]+\.md)")
NAME = re.compile(r"^\d+-[a-z0-9]+(-[a-z0-9]+)*\.md$")


def problems(text: str) -> list[str]:
    """What a page lacks: its status line, or one of the four parts."""
    found = [] if STATUS.search(text) else ["status line"]
    headings = set(re.findall(r"^## (.+?)\s*$", text, re.MULTILINE))
    return found + [part for part in PARTS if part not in headings]


def replaced_by(text: str) -> str | None:
    """The file that replaces this page, or None while the page is in force."""
    status = STATUS.search(text)
    return status[2] if status else None


def readers() -> dict[str, str]:
    """The text of every rule and pipeline doc that may point at a decision page."""
    paths = [
        *ROOT.glob("rules/*.md"),
        *ROOT.glob("skills/**/*.md"),
        ROOT / "CLAUDE.md",
        ROOT / ".claude" / "CLAUDE.md",
        *PAGES,
    ]
    return {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in paths
        if path.is_file()
    }


def test_there_are_pages():
    assert PAGES, "docs/decisions/ is empty"


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_every_page_has_a_status_line_and_the_four_parts(page):
    assert problems(page.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_every_page_is_named_by_its_issue(page):
    assert NAME.match(page.name), f"{page.name}: name it <issue>-<slug>.md"


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_a_replaced_page_points_at_a_page_that_points_back(page):
    new = replaced_by(page.read_text(encoding="utf-8"))
    if new is None:
        return
    target = DECISIONS / new
    assert target.is_file(), f"{page.name}: replaced by {new}, which does not exist"
    assert page.name in REPLACES.findall(target.read_text(encoding="utf-8")), (
        f"{new}: add the line **מחליף:** [{page.name}]({page.name})"
    )


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_a_replacing_page_names_an_old_page_that_says_so(page):
    for old in REPLACES.findall(page.read_text(encoding="utf-8")):
        target = DECISIONS / old
        assert target.is_file(), f"{page.name}: replaces {old}, which does not exist"
        assert replaced_by(target.read_text(encoding="utf-8")) == page.name, (
            f"{old}: set its status line to **מצב:** הוחלף ב-[{page.name}]({page.name})"
        )


def test_every_pointer_to_a_page_names_a_page_that_exists():
    names = {page.name for page in PAGES}
    dead = [
        f"{where}: docs/decisions/{name}"
        for where, text in readers().items()
        for name in POINTER.findall(text)
        if name not in names
    ]
    assert dead == []


def test_the_template_is_a_whole_page():
    assert problems(TEMPLATE.read_text(encoding="utf-8")) == []


GOOD = (
    "**מצב:** בתוקף · **תאריך:** 2026-11-08\n\n"
    "## רקע\n## החלטה\n## חלופות שנדחו\n## מחיר\n"
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (GOOD, []),
        (GOOD.replace("**מצב:** בתוקף", "מצב: בתוקף"), ["status line"]),
        (GOOD.replace("## מחיר\n", ""), ["מחיר"]),
        (GOOD.replace("## רקע", "### רקע"), ["רקע"]),
        ("", ["status line", *PARTS]),
    ],
    ids=["whole", "no-status", "no-cost", "wrong-level", "empty"],
)
def test_problems_names_what_is_missing(text, expected):
    assert problems(text) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("**מצב:** בתוקף", None),
        ("**מצב:** הוחלף ב-[200-new.md](200-new.md)", "200-new.md"),
        ("**מצב:** הוחלף ב-[200-new.md](199-other.md)", None),
    ],
    ids=["in-force", "replaced", "link-mismatch"],
)
def test_replaced_by_reads_the_status_line(status, expected):
    assert replaced_by(status + " · **תאריך:** 2026-11-08\n") == expected
