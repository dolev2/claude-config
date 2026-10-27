"""The shared board sync in dev-setup/actions/project-sync (claude-config #3).

Every repo with the pipeline runs this one copy, so these tests guard all of their
boards.
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
    spec = importlib.util.spec_from_file_location(
        "sync_project", ACTION / "sync_project.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def field(name, *options):
    return {
        "id": name,
        "name": name,
        "options": [{"id": o, "name": o} for o in options],
    }


def test_marker_name_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("SYNC_MARKER", "crm-sync")
    sync = load_sync()
    body = "text\n\n<!-- crm-sync: owner=claude status=explore -->\n"
    assert sync.read_marker(body) == {"owner": "claude", "status": "explore"}
    assert sync.write_marker(body, {"status": "done"}).endswith(
        "<!-- crm-sync: status=done -->\n"
    )
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
    assert sync.choose_winner(marker, {"status": "backlog"}, board) == (
        board,
        "project",
    )


def test_sends_an_all_digit_option_id_as_a_string(monkeypatch):
    # claude-config #4: -F sent "84237580" as a number, and the mutation failed.
    sync = load_sync()
    calls = []
    monkeypatch.setattr(sync, "gh", lambda *args: calls.append(args) or '{"data": {}}')
    sync.graphql("query", option="84237580", number=9)
    args = calls[0]
    assert args[args.index("option=84237580") - 1] == "-f"
    assert args[args.index("number=9") - 1] == "-F"


@pytest.mark.parametrize(
    "options, label, shown",
    [
        (("Backend", "Frontend", "Both", "Infra"), "area:both", "Both"),
        (("Design", "Content", "SEO", "Infra"), "area:seo", "SEO"),
        (("Engine", "Render", "Skills", "Methodology", "Web"), "area:engine", "Engine"),
    ],
)
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
    sync.resolve_options(
        {"Status": field("Status", "Explore (Claude)", board_name, "Done")}
    )
    assert sync.STATUS_OPTIONS["plan-questions"] == board_name
    assert sync.project_state({"Status": board_name}) == {"status": "plan-questions"}


def test_two_labels_of_one_kind_are_reported():
    sync = load_sync()
    assert sync.doubled_dimensions(
        ["status:explore", "status:done", "owner:claude"]
    ) == ["status"]
    assert (
        sync.doubled_dimensions(["status:explore", "owner:claude", "area:infra"]) == []
    )


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
    assert (
        "uses: dolev2/claude-config/skills/dev-setup/actions/project-sync@main"
        in workflow
    )
    assert "actions/checkout" not in workflow
    assert "sync-marker: ${{ vars.SYNC_MARKER }}" in workflow
    assert "if: vars.PROJECT_NUMBER != ''" in workflow


def test_home_repo_workflow_can_read_its_own_action():
    # The run in claude-config itself downloads the action with GITHUB_TOKEN
    # (claude-config #10).
    workflow = (
        ROOT.parents[1] / ".github" / "workflows" / "sync-project.yml"
    ).read_text(encoding="utf-8")
    assert "contents: read" in workflow
    assert (
        "uses: dolev2/claude-config/skills/dev-setup/actions/project-sync@main"
        in workflow
    )


def test_no_workflow_calls_the_old_action_path():
    # The actions moved under skills/ when this repo became ~/.claude (claude-config
    # #6), and the temporary copy at the old path is gone (#23). A workflow on the old
    # path would fail with "Unable to resolve action" in every repo installed from it.
    repo = ROOT.parents[1]
    assert not (repo / "dev-setup").exists()
    workflows = list((repo / ".github" / "workflows").glob("*.yml"))
    workflows += list((ROOT / "templates" / ".github" / "workflows").glob("*.yml"))
    assert workflows
    for workflow in workflows:
        assert "claude-config/dev-setup/" not in workflow.read_text(encoding="utf-8"), (
            workflow.name
        )


def test_no_copy_of_the_sync_script_is_left_to_install():
    assert not (ROOT / "templates" / ".github" / "scripts" / "sync_project.py").exists()


# The sprint view follows the current sprint (claude-config #17).


def milestone(number, title, open_issues):
    return {"number": number, "title": title, "open_issues": open_issues}


def sprint_view(filter_):
    return {"id": "V1", "name": "ספרינט נוכחי", "filter": filter_}


def test_current_sprint_is_the_first_milestone_with_open_issues():
    sync = load_sync()
    milestones = [milestone(3, "M3", 1), milestone(1, "M1", 0), milestone(2, "M2", 4)]
    assert sync.current_sprint(milestones) == "M2"
    assert sync.current_sprint([milestone(1, "M1", 0)]) is None


def test_finished_sprint_moves_the_filter():
    sync = load_sync()
    views = [{"id": "V0", "name": "הכל", "filter": None}, sprint_view('milestone:"M1"')]
    assert sync.sprint_view_change(views, "M2 - Launch") == (
        "V1",
        'milestone:"M2 - Launch"',
    )


def test_a_filter_already_on_the_sprint_is_left_alone():
    sync = load_sync()
    assert sync.sprint_view_change([sprint_view('milestone:"M1"')], "M1") is None


@pytest.mark.parametrize(
    "views, sprint",
    [
        ([sprint_view('milestone:"M1"')], None),  # no milestone has open issues
        (
            [{"id": "V0", "name": "View 1", "filter": 'milestone:"M1"'}],
            "M2",
        ),  # no sprint view
        ([sprint_view("label:bug")], "M2"),  # no milestone term to move
        ([sprint_view(None)], "M2"),
    ],
)
def test_nothing_to_move(views, sprint):
    sync = load_sync()
    assert sync.sprint_view_change(views, sprint) is None


def test_only_the_milestone_term_changes():
    sync = load_sync()
    change = sync.sprint_view_change(
        [sprint_view('label:bug milestone:"Sprint 1" -status:Done')], "Sprint 2"
    )
    assert change == ("V1", 'label:bug milestone:"Sprint 2" -status:Done')
    change = sync.sprint_view_change([sprint_view("milestone:Old")], "New")
    assert change == ("V1", 'milestone:"New"')


def test_sync_sprint_view_sends_the_update(monkeypatch):
    sync = load_sync()
    sent = []
    monkeypatch.setattr(
        sync,
        "gh",
        lambda *args: (
            '[{"number": 1, "title": "M1", "open_issues": 0},'
            ' {"number": 2, "title": "M2", "open_issues": 2}]'
        ),
    )
    monkeypatch.setattr(sync, "graphql", lambda query, **kw: sent.append(kw))
    sync.sync_sprint_view([sprint_view('milestone:"M1"')])
    assert sent == [{"view": "V1", "filter": 'milestone:"M2"'}]


def test_a_failed_view_update_does_not_stop_the_issue_sync(monkeypatch, capsys):
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("PROJECT_NUMBER", "1")
    monkeypatch.setenv("SYNC_MARKER", "x-sync")
    sync = load_sync()
    monkeypatch.setattr(
        sync, "load_project", lambda n: ("P", {}, {}, [sprint_view('milestone:"M1"')])
    )

    def gh(*args):
        if args[0] == "api":
            raise RuntimeError("gh api failed: boom")
        return "[]"  # gh issue list: no issues

    monkeypatch.setattr(sync, "gh", gh)
    sync.main()
    assert "sprint view not updated" in capsys.readouterr().out


# Quiet mode, for the central sweep whose log is public (claude-config #46).


def run_one_label_change(monkeypatch, quiet):
    """main() over one issue whose labels moved; returns what it printed."""
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("PROJECT_NUMBER", "1")
    monkeypatch.setenv("SYNC_MARKER", "x-sync")
    if quiet:
        monkeypatch.setenv("SYNC_QUIET", "1")
    else:
        monkeypatch.delenv("SYNC_QUIET", raising=False)
    sync = load_sync()
    fields = {"Status": field("Status", "Done", "Explore (Claude)")}
    item = {"id": "I5", "values": {"Status": "Explore (Claude)"}}
    monkeypatch.setattr(
        sync,
        "load_project",
        lambda n: ("P", fields, {5: item}, [sprint_view('milestone:"M1"')]),
    )
    monkeypatch.setattr(sync, "graphql", lambda query, **kw: {})
    issue = {
        "number": 5,
        "id": "X5",
        "state": "OPEN",
        "body": "<!-- x-sync: status=explore -->",
        "labels": [{"name": "status:done"}, {"name": "owner:dolev"}],
    }

    def gh(*args):
        if args[0] == "api":
            return '[{"number": 2, "title": "M2", "open_issues": 1}]'
        if args[:2] == ("issue", "list"):
            return sync.json.dumps([issue])
        return ""

    monkeypatch.setattr(sync, "gh", gh)
    sync.main()


def test_quiet_mode_prints_only_the_count(monkeypatch, capsys):
    run_one_label_change(monkeypatch, quiet=True)
    out = capsys.readouterr().out
    assert out == "updated issues: 1\n"


def test_without_quiet_mode_the_output_is_unchanged(monkeypatch, capsys):
    run_one_label_change(monkeypatch, quiet=False)
    out = capsys.readouterr().out
    assert "#5 project <- labels" in out
    assert 'sprint view -> milestone:"M2"' in out
    assert "updated issues" not in out


def test_no_repo_workflow_polls_on_a_schedule():
    # The poll runs centrally from dolev2/.github; a schedule here costs private
    # Actions minutes, which ran out in October 2026 (claude-config #46).
    for workflow in (
        TEMPLATE,
        ROOT.parents[1] / ".github" / "workflows" / "sync-project.yml",
    ):
        text = workflow.read_text(encoding="utf-8")
        assert "schedule:" not in text and "cron:" not in text, workflow
        assert "issues:" in text
