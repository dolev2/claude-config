"""templates/ruleset-main.json: the default branch's protection, as dev-setup sets it.

claude-config#162. The template is the body sent to
`POST repos/{owner}/{repo}/rulesets`, and matches the ruleset set by hand on
claude-config (`protect-main`). These tests pin the rules the pipeline relies on:
a PR for every change, no force push, no deletion, squash only.
"""

import json
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "ruleset-main.json"


@pytest.fixture(scope="module")
def ruleset() -> dict:
    """The template, parsed."""
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def rule(ruleset: dict, kind: str) -> dict:
    """The one rule of this type in the template; fails by name when it is missing."""
    found = [r for r in ruleset["rules"] if r["type"] == kind]
    assert len(found) == 1, f"the template has {len(found)} {kind} rules"
    return found[0]


def test_targets_the_default_branch_of_any_repo(ruleset):
    assert ruleset["name"] == "protect-main"
    assert ruleset["target"] == "branch"
    assert ruleset["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]


def test_is_active_and_nobody_bypasses_it(ruleset):
    assert ruleset["enforcement"] == "active"
    assert ruleset["bypass_actors"] == []


def test_holds_exactly_the_three_rules(ruleset):
    kinds = [r["type"] for r in ruleset["rules"]]
    assert sorted(kinds) == ["deletion", "non_fast_forward", "pull_request"]


def test_pull_request_needs_no_approval_and_merges_by_squash_only(ruleset):
    # Dolev cannot approve a PR opened from his own account, so an approval would block
    # every merge.
    parameters = rule(ruleset, "pull_request")["parameters"]
    assert parameters["required_approving_review_count"] == 0
    assert parameters["required_reviewers"] == []
    assert parameters["require_code_owner_review"] is False
    assert parameters["require_last_push_approval"] is False
    assert parameters["allowed_merge_methods"] == ["squash"]
