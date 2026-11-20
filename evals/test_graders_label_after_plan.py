"""The label grader of the held-out dev-plan case, run on sample label files, no model.

After a plan the issue holds one status label the pipeline still gives: ready to
execute, in review (the code already ran), or plan questions. The plan-approval label
left the pipeline with S-1.64 and fails, like a file with no status label (S-1.69).
"""

import re
from pathlib import Path

import pytest

GRADER = (
    Path(__file__).parent
    / "holdout"
    / "dev-plan-prepare-plan"
    / "graders"
    / "label-after-plan.md"
)


def pattern() -> re.Pattern:
    """The grader's regex, read from the single-quoted `pattern:` line of its file."""
    for line in GRADER.read_text(encoding="utf-8").splitlines():
        if line.startswith("pattern: '") and line.endswith("'"):
            return re.compile(line[len("pattern: '") : -1].replace("''", "'"))
    raise AssertionError("label-after-plan: no pattern line")


def labels_file(*labels: str) -> str:
    """A labels file as the fake gh writes it: sorted, one label per line."""
    return "".join(f"{label}\n" for label in sorted(labels))


@pytest.mark.parametrize(
    "status", ["status:ready-to-execute", "status:in-review", "status:plan-questions"]
)
def test_passes_on_a_pipeline_label(status):
    assert pattern().search(labels_file("task", "area:core", status))


@pytest.mark.parametrize(
    "labels",
    [
        ("task", "area:core", "status:waiting-approval"),
        ("task", "area:core"),
        ("task", "area:core", "status:explore"),
        ("task", "area:core", "status:explore", "status:ready-to-execute"),
    ],
    ids=["plan-approval", "no-status", "still-explore", "explore-not-removed"],
)
def test_fails_on_any_other_status(labels):
    assert not pattern().search(labels_file(*labels))


def test_message_names_the_three_labels():
    message = GRADER.read_text(encoding="utf-8").split("---")[-1]
    for label in ("ready-to-execute", "in-review", "plan-questions"):
        assert f"status:{label}" in message
    assert "waiting-approval" not in message
