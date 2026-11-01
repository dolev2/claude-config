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
