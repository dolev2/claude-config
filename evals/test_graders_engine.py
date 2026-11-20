"""Every regex grader is written in a form the eval engine reads, run with no model.

The engine matches in JavaScript: Python's \\A, \\Z and \\z anchors, and inline flags
like (?m), are not read there, and a grader with one fails even when the skill was
right (S-1.49, S-1.71). This catches them in every PR, before a paid eval run.
"""

from pathlib import Path

import pytest
from graders import is_regex_grader, regex_pattern, unsupported

EVALS = Path(__file__).parent
GRADERS = sorted(
    grader
    for folder in ("cases", "holdout")
    for grader in (EVALS / folder).glob("*/graders/*.md")
    if is_regex_grader(grader)
)


def grader_id(grader: Path) -> str:
    """The grader as <set>/<case>/<grader>, for the test id and the message."""
    return f"{grader.parents[2].name}/{grader.parents[1].name}/{grader.stem}"


def test_finds_graders_in_both_sets():
    sets = {grader.parents[2].name for grader in GRADERS}
    assert sets == {"cases", "holdout"}


@pytest.mark.parametrize("grader", GRADERS, ids=grader_id)
def test_grader_has_nothing_the_engine_cannot_read(grader):
    finds = unsupported(regex_pattern(grader))
    assert not finds, (
        f"{grader_id(grader)}: the eval engine (JavaScript) cannot read "
        + "; ".join(finds)
    )


@pytest.mark.parametrize(
    ("pattern", "fix"),
    [
        (r"\Aopen\n", "^"),
        (r"open\n\Z", "$"),
        (r"open\z", "$"),
        (r"\\\Aopen", "^"),
        (r"(?m)^open$", r"(?:^|\n)<the line>\n"),
        (r"(?s)Plan.*end", r"[\s\S]"),
        (r"(?i:plan)", "both cases"),
        (r"(?ms)^a.b$", r"[\s\S]"),
    ],
    ids=[
        "start-anchor",
        "end-anchor",
        "end-anchor-lower",
        "anchor-after-literal-backslash",
        "flag-m",
        "flag-s",
        "scoped-flag-i",
        "two-flags",
    ],
)
def test_fails_with_the_fix(pattern, fix):
    finds = unsupported(pattern)
    assert len(finds) == 1
    assert fix in finds[0]


@pytest.mark.parametrize(
    "pattern",
    [
        r"\\Aopen",
        r"open\\Z",
        r"(?:^|\n)paused\n",
        r"a(?=b)(?!c)(?<=a)(?<!d)",
        r"\(?m\)",
        r"[\s\S]*#### בקצרה",
        "",
    ],
    ids=[
        "escaped-start",
        "escaped-end",
        "non-capturing-group",
        "lookarounds",
        "escaped-paren",
        "plain",
        "empty",
    ],
)
def test_passes_on_what_the_engine_reads(pattern):
    assert unsupported(pattern) == []


def test_start_and_end_anchors_fail_each_alone():
    assert len(unsupported(r"\Aopen")) == 1
    assert len(unsupported(r"open\Z")) == 1
    assert len(unsupported(r"\Aopen\Z")) == 2


def test_pattern_line_reads_quotes(tmp_path):
    grader = tmp_path / "g.md"
    grader.write_text(
        "---\ntype: regex\npattern: 'it''s\\Z'\n---\nmessage\n", encoding="utf-8"
    )
    assert is_regex_grader(grader)
    assert regex_pattern(grader) == "it's\\Z"


def test_regex_grader_without_pattern_line_fails(tmp_path):
    grader = tmp_path / "g.md"
    grader.write_text('---\ntype: regex\npattern: "x"\n---\n', encoding="utf-8")
    with pytest.raises(AssertionError, match="pattern"):
        regex_pattern(grader)
