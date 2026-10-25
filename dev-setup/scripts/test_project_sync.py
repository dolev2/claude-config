"""The shared board sync in dev-setup/actions/project-sync (claude-config #3).

Every repo with the pipeline runs this one copy, so these tests guard all of their boards.
"""

import importlib.util
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "actions" / "project-sync"
TEMPLATE = ROOT / "templates" / ".github" / "workflows" / "sync-project.yml"
os.environ.setdefault("GITHUB_REPOSITORY", "dolev2/example")


def load_sync():
    spec = importlib.util.spec_from_file_location("sync_project", ACTION / "sync_project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def field(name, *options):
    return {"id": name, "name": name, "options": [{"id": o, "name": o} for o in options]}


def test_marker_name_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("SYNC_MARKER", "crm-sync")
    sync = load_sync()
    body = "text\n\n<!-- crm-sync: owner=claude status=explore -->\n"
    assert sync.read_marker(body) == {"owner": "claude", "status": "explore"}
    assert sync.write_marker(body, {"status": "done"}).endswith("<!-- crm-sync: status=done -->\n")
    assert sync.read_marker("<!-- wayout-sync: owner=claude -->") == {}
    assert sync.PROJECT_OWNER == "dolev2"


def test_a_missing_marker_name_stops_the_run(monkeypatch):
    # A default name would make every issue look unsynced, and the board would win.
    monkeypatch.delenv("SYNC_MARKER", raising=False)
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("PROJECT_NUMBER", "1")
    sync = load_sync()
    with pytest.raises(SystemExit, match="SYNC_MARKER"):
        sync.check_environment()


def test_blank_board_takes_the_labels_even_when_the_marker_matches():
    sync = load_sync()
    state = {"owner": "claude", "status": "explore"}
    assert sync.choose_winner(state, state, {}) == (state, "labels")
    assert sync.choose_winner(state, state, state) == (None, None)
    assert sync.choose_winner({}, {}, {}) == (None, None)


def test_board_edit_wins_over_labels():
    sync = load_sync()
    marker = {"status": "explore"}
    board = {"status": "done"}
    assert sync.choose_winner(marker, {"status": "backlog"}, board) == (board, "project")


def test_sends_an_all_digit_option_id_as_a_string(monkeypatch):
    # claude-config #4: -F sent "84237580" as a number, and the mutation failed.
    sync = load_sync()
    calls = []
    monkeypatch.setattr(sync, "gh", lambda *args: calls.append(args) or '{"data": {}}')
    sync.graphql("query", option="84237580", number=9)
    args = calls[0]
    assert args[args.index("option=84237580") - 1] == "-f"
    assert args[args.index("number=9") - 1] == "-F"


@pytest.mark.parametrize("options, label, shown", [
    (("Backend", "Frontend", "Both", "Infra"), "area:both", "Both"),
    (("Design", "Content", "SEO", "Infra"), "area:seo", "SEO"),
    (("Engine", "Render", "Skills", "Methodology", "Web"), "area:engine", "Engine"),
])
def test_areas_are_read_from_the_board(options, label, shown):
    sync = load_sync()
    sync.resolve_options({"Area": field("Area", *options)})
    assert sync.labels_state([label]) == {"area": label.split(":")[1]}
    assert sync.project_state({"Area": shown}) == {"area": label.split(":")[1]}


def test_an_area_the_board_lacks_is_left_out():
    sync = load_sync()
    sync.resolve_options({"Area": field("Area", "Design", "Infra")})
    assert sync.labels_state(["area:backend", "owner:claude"]) == {"owner": "claude"}


@pytest.mark.parametrize("board_name", ["Plan questions", "Plan questions (Dolev)"])
def test_plan_questions_matches_either_board_name(board_name):
    sync = load_sync()
    sync.resolve_options({"Status": field("Status", "Explore (Claude)", board_name, "Done")})
    assert sync.STATUS_OPTIONS["plan-questions"] == board_name
    assert sync.project_state({"Status": board_name}) == {"status": "plan-questions"}


def test_two_labels_of_one_kind_are_reported():
    sync = load_sync()
    assert sync.doubled_dimensions(["status:explore", "status:done", "owner:claude"]) == ["status"]
    assert sync.doubled_dimensions(["status:explore", "owner:claude", "area:infra"]) == []


def test_action_runs_a_script_that_exists():
    # A rename here would break every board at once, silently.
    action = (ACTION / "action.yml").read_text(encoding="utf-8")
    assert "using: composite" in action
    scripts = re.findall(r"\$\{\{ github\.action_path \}\}/([\w./-]+\.py)", action)
    assert scripts, "action.yml no longer runs a script from its own folder"
    for script in scripts:
        assert (ACTION / script).is_file(), script


def test_template_calls_the_shared_action_at_main_without_checkout():
    workflow = TEMPLATE.read_text(encoding="utf-8")
    assert "uses: dolev2/claude-config/dev-setup/actions/project-sync@main" in workflow
    assert "actions/checkout" not in workflow
    assert "sync-marker: ${{ vars.SYNC_MARKER }}" in workflow
    assert "if: vars.PROJECT_NUMBER != ''" in workflow


def test_home_repo_workflow_can_read_its_own_action():
    # The run in claude-config itself downloads the action with GITHUB_TOKEN (claude-config #10).
    workflow = (ROOT.parent / ".github" / "workflows" / "sync-project.yml").read_text(encoding="utf-8")
    assert "contents: read" in workflow
    assert "uses: dolev2/claude-config/dev-setup/actions/project-sync@main" in workflow


def test_no_copy_of_the_sync_script_is_left_to_install():
    assert not (ROOT / "templates" / ".github" / "scripts" / "sync_project.py").exists()
