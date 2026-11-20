import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import merge_declines  # noqa: E402

REPO = "https://api.github.com/repos/acme/widgets/issues"
HEAD = "4f2a9c0d1e2b3a4f5c6d7e8f9a0b1c2d3e4f5a6b"


def comment(number, body):
    return {"issue_url": f"{REPO}/{number}", "body": body}


def decline(sha=HEAD, marker="<!-- orchestrator -->"):
    return f"{marker}\n<!-- merge-declined: {sha} -->\nדולב דחה את המיזוג."


def declined(comments, number=1, head=HEAD):
    found = merge_declines.declined_heads(comments)
    return merge_declines.is_declined(found, number, head)


def test_an_orchestrator_decline_of_the_current_head_counts():
    assert declined([comment(1, decline())])


def test_a_short_sha_matches_the_head_it_starts():
    assert declined([comment(1, decline(HEAD[:7]))])


def test_a_new_head_after_a_repair_round_brings_the_pr_back():
    assert not declined([comment(1, decline())], head="9" * 40)


@pytest.mark.parametrize(
    "body",
    [
        decline(marker=""),  # a child, or anyone else, writing the marker
        f"<!-- orchestrator -->\nטקסט: <!-- merge-declined: {HEAD} --> באמצע שורה",
    ],
)
def test_a_marker_outside_an_orchestrator_line_of_its_own_does_not_count(body):
    assert not declined([comment(1, body)])


def test_a_decline_on_another_issue_does_not_count():
    assert not declined([comment(2, decline())])


def test_no_comments_no_decline():
    assert merge_declines.declined_heads([]) == set()
    assert not declined([])
