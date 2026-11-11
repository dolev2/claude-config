"""The `gh api graphql` side of fake_gh.py: the one issue query the pipeline docs use.

reference/issue-body.md reads an issue's sub-issues and cross-references in one query;
this answers any query on `issue(number:)` with those connections and `blockedBy`.
Any other query is unsupported, so a case never passes on a query nobody simulated.
"""

from __future__ import annotations

import re

from fake_gh_state import GhError, State


def node(state: State, number: int) -> dict:
    """number, title and state of an issue or PR, as a GraphQL node."""
    if str(number) in state.data["issues"]:
        issue = state.issue(number)
        return {
            "number": number,
            "title": issue.get("title", ""),
            "state": issue.get("state", "open").upper(),
        }
    pull = state.pull(number)
    return {
        "number": number,
        "title": pull.get("title", ""),
        "state": state.pull_status(pull).upper(),
    }


def issue_query(state: State, number: int) -> dict:
    """The issue's sub-issues, blockers, and the PRs that cross-reference it."""
    issue = state.issue(number)
    events = [{"source": node(state, pr)} for pr in state.closing_pulls(number)]
    return {
        "number": number,
        "title": issue.get("title", ""),
        "state": issue.get("state", "open").upper(),
        "body": issue.get("body", ""),
        "subIssues": {"nodes": [node(state, n) for n in issue.get("sub_issues", [])]},
        "blockedBy": {"nodes": [node(state, n) for n in issue.get("blocked_by", [])]},
        "timelineItems": {"nodes": events},
    }


def handle(query: str, variables: dict, state: State) -> dict:
    """Answer a GraphQL query on one issue; GhError for anything else."""
    number = variables.get("num") or variables.get("number")
    if number is None:
        match = re.search(r"issue\(number:\s*(\d+)\)", query)
        number = match[1] if match else None
    if "issue(" not in query or number is None:
        raise GhError("fake gh: unsupported: graphql query", unsupported=True)
    issue = issue_query(state, int(number))
    return {"data": {"repository": {"issue": issue}}}
