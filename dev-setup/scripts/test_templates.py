"""The .github/scripts templates that dev-setup copies into a repo."""

import importlib.util
import os
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "templates" / ".github" / "scripts"
os.environ.setdefault("GITHUB_REPOSITORY", "dolev2/example")


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sync_marker_name_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("SYNC_MARKER", "crm-sync")
    sync = load("sync_project")
    body = "text\n\n<!-- crm-sync: owner=claude status=explore -->\n"
    assert sync.read_marker(body) == {"owner": "claude", "status": "explore"}
    assert sync.write_marker(body, {"status": "done"}).endswith("<!-- crm-sync: status=done -->\n")
    assert sync.read_marker("<!-- wayout-sync: owner=claude -->") == {}
    assert sync.PROJECT_OWNER == "dolev2"


def test_sync_marker_defaults_to_pipeline_sync(monkeypatch):
    monkeypatch.delenv("SYNC_MARKER", raising=False)
    sync = load("sync_project")
    assert sync.write_marker("x", {"owner": "claude"}).endswith("<!-- pipeline-sync: owner=claude -->\n")


def test_sync_blank_board_takes_the_labels_even_when_the_marker_matches():
    sync = load("sync_project")
    state = {"owner": "claude", "status": "explore"}
    assert sync.choose_winner(state, state, {}) == (state, "labels")
    assert sync.choose_winner(state, state, state) == (None, None)
    assert sync.choose_winner({}, {}, {}) == (None, None)


def test_sync_board_edit_wins_over_labels():
    sync = load("sync_project")
    marker = {"status": "explore"}
    board = {"status": "done"}
    assert sync.choose_winner(marker, {"status": "backlog"}, board) == (board, "project")


def test_sync_sends_an_all_digit_option_id_as_a_string(monkeypatch):
    # claude-skills #4: -F sent "84237580" as a number, and the mutation failed.
    sync = load("sync_project")
    calls = []
    monkeypatch.setattr(sync, "gh", lambda *args: calls.append(args) or '{"data": {}}')
    sync.graphql("query", option="84237580", number=9)
    args = calls[0]
    assert args[args.index("option=84237580") - 1] == "-f"
    assert args[args.index("number=9") - 1] == "-F"

