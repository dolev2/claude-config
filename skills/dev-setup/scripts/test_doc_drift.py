"""Drift checks: the pipeline knowledge that is written twice stays the same (#248).

Three drift checks, kept by a test and not by hand (reference/owners.md): the two
lifecycle pages, the test commands in .claude/CLAUDE.md and README.md against tests.yml,
and the files and skills the owners map names. The spec-check and size-check actions are
uses: steps with no documented command; test_spec_check.py and test_size_check.py cover
them.
"""

import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "skills" / "dev-setup" / "reference"

PAGES = ("issue-lifecycle.html", "issue-lifecycle-en.html")
SHAPE_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "li", "tr")


class PageShape(HTMLParser):
    """Counts a page's headings, list items, table rows and rule cards, and its ids."""

    def __init__(self):
        super().__init__()
        self.counts = dict.fromkeys([*SHAPE_TAGS, "rule"], 0)
        self.ids: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in self.counts:
            self.counts[tag] += 1
        # The exact class word: class="rules" is the container, not a card.
        if "rule" in (attributes.get("class") or "").split():
            self.counts["rule"] += 1
        if attributes.get("id"):
            self.ids.append(attributes["id"])


def page_shape(html: str) -> PageShape:
    shape = PageShape()
    shape.feed(html)
    return shape


def shape_gaps(hebrew: str, english: str) -> list[str]:
    """What differs between the two lifecycle pages, one line per difference."""
    he, en = page_shape(hebrew), page_shape(english)
    gaps = [
        f"{key}: {he.counts[key]} in {PAGES[0]}, {en.counts[key]} in {PAGES[1]}"
        for key in he.counts
        if he.counts[key] != en.counts[key]
    ]
    if he.ids != en.ids:
        gaps.append(f"ids: {he.ids} in {PAGES[0]}, {en.ids} in {PAGES[1]}")
    return gaps


def test_the_two_lifecycle_pages_have_the_same_shape():
    hebrew, english = ((REFERENCE / page).read_text(encoding="utf-8") for page in PAGES)
    gaps = shape_gaps(hebrew, english)
    assert gaps == [], (
        f"the two pages drifted: {gaps}. Translate the change to the other page in "
        "the same PR (.claude/CLAUDE.md, 'שתי הגרסאות מתארות אותו תהליך')"
    )


def test_page_shape_catches_a_missing_item_and_a_changed_id():
    page = '<h2 id="a">x</h2><ul class="rules"><li class="rule">1</li><li>2</li></ul>'
    assert shape_gaps(page, page) == []
    gaps = shape_gaps(page, page.replace("<li>2</li>", ""))
    assert gaps == [f"li: 2 in {PAGES[0]}, 1 in {PAGES[1]}"]
    assert shape_gaps(page, page.replace('id="a"', 'id="b"'))[0].startswith("ids:")
    # class="rules" is the container: only the exact class word counts as a card.
    assert page_shape(page).counts["rule"] == 1
    gaps = shape_gaps(page, page.replace('<li class="rule">', "<li>"))
    assert gaps == [f"rule: 1 in {PAGES[0]}, 0 in {PAGES[1]}"]


# Single-line run: steps only; a "run: |" block would read as the command "|".
RUN_LINE = re.compile(r"^\s*(?:-\s+)?run:\s*(\S.*)$", re.MULTILINE)
# An argument only CI passes, from a workflow expression: --base origin/${{ ... }}.
CI_ONLY_ARGUMENT = re.compile(r"\s+--[\w-]+[ =]\S*\$\{\{.*?\}\}\S*")
TESTS_HEADING = re.compile(r"^## בדיקות\s*$", re.MULTILINE)
NEXT_SECTION = re.compile(r"^## ", re.MULTILINE)
INSTALL_LINE = re.compile(r"בסביבה נקייה: קודם `([^`]+)`")


def workflow_commands(workflow: str) -> tuple[str, list[str]]:
    """The pip install line of tests.yml, and its other run: lines in order."""
    runs = [CI_ONLY_ARGUMENT.sub("", run).strip() for run in RUN_LINE.findall(workflow)]
    installs = [run for run in runs if run.startswith("pip install")]
    install = installs[0] if installs else ""
    return install, [run for run in runs if run not in installs]


def doc_commands(text: str) -> tuple[str, list[str]]:
    """The install line and the first code block of a doc's '## בדיקות' section.

    A missing part reads as empty, so the gap names the file instead of crashing.
    """
    heading = TESTS_HEADING.search(text)
    if not heading:
        return "", []
    section = NEXT_SECTION.split(text[heading.end() :], maxsplit=1)[0]
    block = re.search(r"```[^\n]*\n(.*?)```", section, re.DOTALL)
    install = INSTALL_LINE.search(section)
    lines = [line.strip() for line in block.group(1).splitlines()] if block else []
    return (install.group(1) if install else ""), [line for line in lines if line]


def command_gaps(where: str, doc: str, workflow: str) -> list[str]:
    """How a doc's test commands differ from what tests.yml really runs."""
    ci_install, ci_runs = workflow_commands(workflow)
    install, runs = doc_commands(doc)
    gaps = []
    if runs != ci_runs:
        missing = [run for run in ci_runs if run not in runs]
        extra = [run for run in runs if run not in ci_runs]
        gaps.append(f"{where}: commands {runs}, CI runs {ci_runs}")
        gaps += [f"{where}: missing {missing}"] if missing else []
        gaps += [f"{where}: extra {extra}"] if extra else []
    if install != ci_install:
        gaps.append(f"{where}: install `{install}`, CI installs `{ci_install}`")
    return gaps


def test_the_documented_test_commands_match_ci():
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )
    gaps = [
        gap
        for where in (".claude/CLAUDE.md", "README.md")
        for gap in command_gaps(
            where, (ROOT / where).read_text(encoding="utf-8"), workflow
        )
    ]
    assert gaps == [], (
        f"{gaps}. .github/workflows/tests.yml is what CI really runs; the owner of the "
        "commands is .claude/CLAUDE.md, and README.md copies it (reference/owners.md)"
    )


WORKFLOW = """
      - run: pip install pytest ruff==1
      - run: ruff check .
      - uses: ./skills/dev-setup/actions/spec-check
      - if: github.event_name == 'pull_request'
        run: python check.py --base origin/${{ github.base_ref }}
"""
DOC = """## בדיקות
```
ruff check .
python check.py
```
בסביבה נקייה: קודם `pip install pytest ruff==1`.
"""


@pytest.mark.parametrize(
    "doc, expected",
    [
        (DOC.replace("ruff check .\n", ""), "missing ['ruff check .']"),
        (
            DOC.replace("python check.py\n", "python extra.py\n"),
            "extra ['python extra.py']",
        ),
        (
            DOC.replace(
                "ruff check .\npython check.py", "python check.py\nruff check ."
            ),
            "commands",
        ),
        (DOC.replace("ruff==1", "ruff==2"), "install `pip install pytest ruff==2`"),
        (
            DOC.replace("## בדיקות", "## אחר"),
            "missing ['ruff check .', 'python check.py']",
        ),
    ],
)
def test_command_gaps_name_the_file_and_the_drift(doc, expected):
    assert command_gaps("README.md", DOC, WORKFLOW) == []
    gaps = command_gaps("README.md", doc, WORKFLOW)
    assert any(gap.startswith("README.md:") and expected in gap for gap in gaps), gaps


OWNER_NAME = re.compile(r"`([^`\s]+\.md|dev-[\w*-]+)`")


def owner_path(name: str) -> Path:
    """The file a name in owners.md stands for (a skill name: its SKILL.md)."""
    if name.startswith("dev-"):
        return ROOT / "skills" / name / "SKILL.md"
    if name.startswith("~/.claude/"):
        return ROOT / name.removeprefix("~/.claude/")
    if "/" in name:
        return ROOT / name
    return REFERENCE / name if (REFERENCE / name).is_file() else ROOT / name


def missing_owners(table: str) -> list[str]:
    """Each name in the owners map with no file behind it, with its row."""
    return [
        f"{name}, in the row: {row.split('|')[1].strip()}"
        for row in table.splitlines()
        if row.startswith("| ") and not row.startswith("| הכלל")
        for name in OWNER_NAME.findall(row)
        if "*" not in name and not owner_path(name).is_file()
    ]


def test_every_file_the_owners_map_names_exists():
    missing = missing_owners((REFERENCE / "owners.md").read_text(encoding="utf-8"))
    assert missing == [], f"fix these names in reference/owners.md: {missing}"


def test_missing_owners_names_a_wrong_file_and_a_wrong_skill():
    row = "| a rule | `pipeline.md` | `dev-plan`, `dev-*`, `~/.claude/rules/git.md` |"
    assert missing_owners(row) == []
    broken = row.replace("pipeline.md", "pipline.md").replace("dev-plan", "dev-plon")
    assert missing_owners(broken) == [
        "pipline.md, in the row: a rule",
        "dev-plon, in the row: a rule",
    ]
