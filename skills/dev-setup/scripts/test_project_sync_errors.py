"""Two failures of the board sync: an issue already on the board (claude-config #101),
and a transient server error from GitHub (claude-config #105)."""

import json
import subprocess

import board
import gh_api
import pytest
import sync_project

# An issue node as ONE_ISSUE_ITEMS returns it, on board 1 with its Status.
ON_BOARD = {
    "number": 126,
    "projectItems": {
        "nodes": [
            {
                "id": "I126",
                "project": {"number": 1},
                "fieldValues": {
                    "nodes": [
                        {"name": "Backlog", "field": {"name": "Status"}},
                        {},
                    ]
                },
            }
        ]
    },
}
ISSUE = {"number": 126, "id": "X126"}


def graphql_that_finds(node, add_error):
    """A graphql() whose add fails with add_error and whose read returns node."""

    def graphql(query, **variables):
        if query == board.ADD_ITEM:
            raise RuntimeError(add_error)
        return {"data": {"repository": {"issue": node}}}

    return graphql


def test_an_issue_already_on_the_board_goes_on_with_its_item(monkeypatch):
    error = "gh api graphql -f failed: gh: Content already exists in this project"
    monkeypatch.setattr(gh_api, "graphql", graphql_that_finds(ON_BOARD, error))
    item = board.add_item("P", "dolev2/charging-crm", 1, ISSUE)
    assert item == ({"id": "I126", "values": {"Status": "Backlog"}}, False)


def test_already_on_the_board_but_not_found_still_fails(monkeypatch):
    error = "gh: Content already exists in this project"
    off_board = {"number": 126, "projectItems": {"nodes": []}}
    monkeypatch.setattr(gh_api, "graphql", graphql_that_finds(off_board, error))
    with pytest.raises(RuntimeError, match="already exists"):
        board.add_item("P", "dolev2/charging-crm", 1, ISSUE)


def test_another_add_error_still_fails(monkeypatch):
    monkeypatch.setattr(
        gh_api, "graphql", graphql_that_finds(ON_BOARD, "gh: Resource not accessible")
    )
    with pytest.raises(RuntimeError, match="not accessible"):
        board.add_item("P", "dolev2/charging-crm", 1, ISSUE)


def test_a_new_issue_gets_an_empty_item(monkeypatch):
    added = {"data": {"addProjectV2ItemById": {"item": {"id": "I7"}}}}
    monkeypatch.setattr(gh_api, "graphql", lambda query, **kw: added)
    assert board.add_item("P", "dolev2/x", 1, ISSUE) == (
        {"id": "I7", "values": {}},
        True,
    )


def test_the_sync_goes_on_with_the_item_already_on_the_board(monkeypatch, capsys):
    # The read at the start of the run missed the card (charging-crm #126).
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("PROJECT_NUMBER", "1")
    monkeypatch.delenv("SYNC_QUIET", raising=False)
    status = {
        "id": "Status",
        "name": "Status",
        "options": [
            {"id": "o-backlog", "name": "Backlog"},
            {"id": "o-done", "name": "Done"},
        ],
    }
    monkeypatch.setattr(
        board, "load_project", lambda o, r, n: ("P", {"Status": status}, {}, [])
    )
    error = "gh: Content already exists in this project"
    sets = []

    def graphql(query, **kw):
        if query == board.SET_SELECT:
            sets.append(kw)
            return {}
        return graphql_that_finds(ON_BOARD, error)(query, **kw)

    monkeypatch.setattr(gh_api, "graphql", graphql)
    issue = {**ISSUE, "state": "OPEN", "labels": [{"name": "status:done"}]}

    def gh(*args):
        if args[:2] == ("issue", "list"):
            return json.dumps([issue])
        return "[]"

    monkeypatch.setattr(gh_api, "gh", gh)
    sync_project.main()
    assert sets == [
        {"project": "P", "item": "I126", "field": "Status", "option": "o-done"}
    ]
    assert "added to the project" not in capsys.readouterr().out


# The retry in gh_api.gh, with the gh CLI and the waits replaced.

UNAVAILABLE = "gh: No server is currently available to service your request. (HTTP 503)"


def fake_runs(monkeypatch, *results: tuple[int, str]) -> list[float]:
    """Make gh answer with results in order; return the waits it slept."""
    answers = iter(results)
    waits = []

    def run(args, **kw):
        code, text = next(answers)
        out, err = (text, "") if code == 0 else ("", text)
        return subprocess.CompletedProcess(args, code, out, err)

    monkeypatch.setattr(gh_api.subprocess, "run", run)
    monkeypatch.setattr(gh_api.time, "sleep", waits.append)
    return waits


def test_a_503_and_then_success_returns_the_output(monkeypatch):
    waits = fake_runs(monkeypatch, (1, UNAVAILABLE), (0, "ok"))
    assert gh_api.gh("api", "graphql") == "ok"
    assert waits == [2]


def test_a_503_that_does_not_pass_fails_after_three_tries(monkeypatch):
    waits = fake_runs(monkeypatch, *[(1, UNAVAILABLE)] * 3)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        gh_api.gh("api", "graphql")
    assert waits == [2, 5]


@pytest.mark.parametrize("code", ["502", "504"])
def test_502_and_504_are_tried_again(monkeypatch, code):
    waits = fake_runs(monkeypatch, (1, f"gh: Bad gateway (HTTP {code})"), (0, "ok"))
    assert gh_api.gh("api", "graphql") == "ok"
    assert waits == [2]


def test_another_error_fails_at_once(monkeypatch):
    waits = fake_runs(monkeypatch, (1, "gh: Not Found (HTTP 404)"))
    with pytest.raises(RuntimeError, match="HTTP 404"):
        gh_api.gh("api", "graphql")
    assert waits == []
