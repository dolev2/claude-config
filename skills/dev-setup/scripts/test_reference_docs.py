"""reference/*.md: every pointer to a reference file is live, and the files stay small.

The skills point at reference files by name, never at a heading inside one
(claude-config#99), so a renamed heading cannot break a pointer. These tests guard the
names instead.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT / "skills" / "dev-setup" / "reference"
DOCS = sorted(REFERENCE.glob("*.md"))
MAX_LINES = 150
POINTER = re.compile(r"reference/([\w-]+\.md)")


def readers() -> dict[str, str]:
    """The text of every file that may point at a reference file, by its repo path."""
    paths = [
        *ROOT.glob("skills/*/SKILL.md"),
        *ROOT.glob("rules/*.md"),
        ROOT / "CLAUDE.md",
        ROOT / ".claude" / "CLAUDE.md",
        *ROOT.glob("skills/dev-setup/**/*.py"),
    ]
    return {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in paths
        if path.is_file()
    }


def test_every_pointer_names_a_file_that_exists():
    names = {doc.name for doc in DOCS}
    dead = [
        f"{where}: reference/{name}"
        for where, text in readers().items()
        for name in POINTER.findall(text)
        if name not in names
    ]
    assert dead == []


@pytest.mark.parametrize("doc", DOCS, ids=lambda doc: doc.name)
def test_every_reference_file_has_a_reader(doc):
    assert any(f"reference/{doc.name}" in text for text in readers().values())


def test_the_core_lists_every_other_reference_file():
    core = (REFERENCE / "pipeline.md").read_text(encoding="utf-8")
    listed = set(re.findall(r"^\| `([\w-]+\.md)` \|", core, re.MULTILINE))
    assert listed == {doc.name for doc in DOCS} - {"pipeline.md"}


def test_no_skill_points_at_the_reference_doc_without_a_file_name():
    vague = [
        where
        for where, text in readers().items()
        if where.endswith("SKILL.md") and "reference doc" in text
    ]
    assert vague == []


@pytest.mark.parametrize("doc", DOCS, ids=lambda doc: doc.name)
def test_reference_file_stays_small(doc):
    lines = doc.read_text(encoding="utf-8").count("\n")
    assert lines <= MAX_LINES, f"{doc.name}: {lines} lines; split it or cut it"


GH_COMMAND = re.compile(r"\bgh (issue|pr) ([a-z][a-z-]*)")


def cloud_table() -> str:
    """The section of cloud.md that maps each gh command to its cloud replacement."""
    text = (REFERENCE / "cloud.md").read_text(encoding="utf-8")
    start = text.index("## פקודות GitHub בסשן ענן")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else None]


def gh_sources() -> list[Path]:
    """The skills and reference docs whose gh commands the cloud table must cover."""
    paths = [*ROOT.glob("skills/*/SKILL.md"), *DOCS]
    return [path for path in paths if path.name != "cloud.md"]


def test_cloud_table_covers_every_gh_issue_and_pr_command():
    used = {
        f"gh {group} {verb}"
        for path in gh_sources()
        for group, verb in GH_COMMAND.findall(path.read_text(encoding="utf-8"))
    }
    table = cloud_table()
    missing = sorted(
        command
        for command in used
        if not re.search(re.escape(command) + r"(?![\w-])", table)
    )
    assert missing == [], f"add a row to the table in reference/cloud.md for: {missing}"


# ASCII only, so a Hebrew word after --json is not a field. Quotes and = are allowed.
JSON_FIELDS = re.compile(r"--json[=\s]+[\"']?([A-Za-z,]+)")


def json_fields_used() -> dict[str, set[str]]:
    """Each --json field a skill or reference doc asks gh issue/pr for, with where."""
    used: dict[str, set[str]] = {}
    for path in gh_sources():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not GH_COMMAND.search(line):
                continue
            for group in JSON_FIELDS.findall(line):
                for field in filter(None, group.split(",")):
                    used.setdefault(field, set()).add(path.relative_to(ROOT).as_posix())
    return used


def test_cloud_table_covers_every_json_field():
    # No exception list: a field that keeps its name in REST is still named in the
    # section (item 6), so a look-alike such as url (REST: html_url) gets documented.
    # One hyphen may precede it (ה-milestone), but a flag like --state does not count.
    table = cloud_table()
    missing = sorted(
        f"{field} ({', '.join(sorted(where))})"
        for field, where in json_fields_used().items()
        if not re.search(r"(?<!\w)(?<!--)" + re.escape(field) + r"(?![\w-])", table)
    )
    assert missing == [], (
        f"name these --json fields and their REST form in reference/cloud.md: {missing}"
    )
