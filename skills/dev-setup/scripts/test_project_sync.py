"""The shared board sync in dev-setup/actions/project-sync (claude-config #3).

Every repo with the pipeline runs this one copy, so these tests guard all of their
boards. The rules alone are in test_sync_rules.py, the sprint view in
test_sprint_view.py, and the two failures of #101 and #105 in
test_project_sync_errors.py.
"""

import ast
import json
import os
import re
import sys
from pathlib import Path

import board
import gh_api
import pytest
import sync_project

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "actions" / "project-sync"
TEMPLATE = ROOT / "templates" / ".github" / "workflows" / "sync-project.yml"
os.environ.setdefault("GITHUB_REPOSITORY", "dolev2/example")


def field(name, *options):
    return {
        "id": name,
        "name": name,
        "options": [{"id": o, "name": o} for o in options],
    }


def sprint_view(filter_):
    return {"id": "V1", "name": "ספרינט נוכחי", "filter": filter_}


def set_environment(monkeypatch, quiet=False):
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("PROJECT_NUMBER", "1")
    monkeypatch.delenv("SYNC_MARKER", raising=False)
    if quiet:
        monkeypatch.setenv("SYNC_QUIET", "1")
    else:
        monkeypatch.delenv("SYNC_QUIET", raising=False)


def test_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("PROJECT_NUMBER", "9")
    monkeypatch.delenv("PROJECT_OWNER", raising=False)
    settings = sync_project.load_settings()
    assert settings.project_number == 9
    assert settings.project_owner == "dolev2"


def test_the_run_needs_no_marker_name(monkeypatch):
    # The hidden marker is gone (#111); a repo installed before it may still set one.
    set_environment(monkeypatch)
    sync_project.check_environment()


def test_a_missing_project_number_stops_the_run(monkeypatch):
    set_environment(monkeypatch)
    monkeypatch.delenv("PROJECT_NUMBER")
    with pytest.raises(SystemExit, match="PROJECT_NUMBER"):
        sync_project.check_environment()


def test_sends_an_all_digit_option_id_as_a_string(monkeypatch):
    # claude-config #4: -F sent "84237580" as a number, and the mutation failed.
    calls = []
    monkeypatch.setattr(
        gh_api, "gh", lambda *args: calls.append(args) or '{"data": {}}'
    )
    gh_api.graphql("query", option="84237580", number=9)
    args = calls[0]
    assert args[args.index("option=84237580") - 1] == "-f"
    assert args[args.index("number=9") - 1] == "-F"


def imported_modules(path: Path) -> set[str]:
    """The top-level names of every module the file imports."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    return names


def test_every_local_import_ships_in_the_folder():
    # sync-boards.yml in dolev2/.github downloads the folder's .py files and action.yml
    # runs them in place; an import of a module that is not there breaks every board
    # (claude-config #57).
    local = {p.stem for p in ACTION.glob("*.py")}
    for path in ACTION.glob("*.py"):
        for name in imported_modules(path):
            assert name in local or name in sys.stdlib_module_names, (
                f"{path.name} imports {name}"
            )


def test_no_file_of_the_sync_grows_past_the_limit():
    # The split of claude-config #57: about 300 lines a file (rules/code-general.md).
    for path in ACTION.glob("*.py"):
        lines = path.read_text(encoding="utf-8").count("\n")
        assert lines <= 300, f"{path.name}: {lines} lines"


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
    assert "sync-marker" not in workflow  # gone with the marker (#111)
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


# The loop over issues, end to end with gh replaced.


def test_a_failed_view_update_does_not_stop_the_issue_sync(monkeypatch, capsys):
    set_environment(monkeypatch)
    monkeypatch.setattr(
        board,
        "load_project",
        lambda o, r, n: ("P", {}, {}, [sprint_view('milestone:"M1"')]),
    )

    def gh(*args):
        if args[0] == "api":
            raise RuntimeError("gh api failed: boom")
        return "[]"  # gh issue list: no issues

    monkeypatch.setattr(gh_api, "gh", gh)
    sync_project.main()
    assert "sprint view not updated" in capsys.readouterr().out


# Quiet mode, for the central sweep whose log is public (claude-config #46).


def run_one_label_change(monkeypatch, quiet) -> list[tuple]:
    """main() over one issue whose labels moved; the gh calls it made."""
    set_environment(monkeypatch, quiet)
    fields = {"Status": field("Status", "Done", "Explore (Claude)")}
    item = {"id": "I5", "values": {"Status": "Explore (Claude)"}}
    monkeypatch.setattr(
        board,
        "load_project",
        lambda o, r, n: ("P", fields, {5: item}, [sprint_view('milestone:"M1"')]),
    )
    monkeypatch.setattr(gh_api, "graphql", lambda query, **kw: {})
    issue = {
        "number": 5,
        "id": "X5",
        "state": "OPEN",
        "body": "<!-- x-sync: status=explore -->",  # an old marker, now ignored
        "labels": [{"name": "status:done"}, {"name": "task"}],
    }
    calls = []

    def gh(*args):
        calls.append(args)
        if args[0] == "api":
            return '[{"number": 2, "title": "M2", "open_issues": 1}]'
        if args[:2] == ("issue", "list"):
            return json.dumps([issue])
        return ""

    monkeypatch.setattr(gh_api, "gh", gh)
    sync_project.main()
    return calls


def test_a_label_change_never_edits_the_body(monkeypatch):
    calls = run_one_label_change(monkeypatch, quiet=True)
    assert not [args for args in calls if "--body-file" in args]
    assert not [args for args in calls if args[:2] == ("issue", "edit")]


def test_quiet_mode_prints_only_the_counts(monkeypatch, capsys):
    run_one_label_change(monkeypatch, quiet=True)
    out = capsys.readouterr().out
    assert out == "updated issues: 1\nactive without a sprint: 0\n"


def test_without_quiet_mode_the_output_is_unchanged(monkeypatch, capsys):
    run_one_label_change(monkeypatch, quiet=False)
    out = capsys.readouterr().out
    assert "#5 project <- labels" in out
    assert 'sprint view -> milestone:"M2"' in out
    assert "updated issues" not in out


def test_an_issue_opened_from_the_board_takes_its_labels(monkeypatch, capsys):
    set_environment(monkeypatch)
    fields = {"Status": field("Status", "Backlog")}
    item = {"id": "I9", "values": {"Status": "Backlog"}}
    monkeypatch.setattr(
        board, "load_project", lambda o, r, n: ("P", fields, {9: item}, [])
    )
    issue = {"number": 9, "id": "X9", "state": "OPEN", "body": "", "labels": []}
    edits = []

    def gh(*args):
        if args[0] == "api":
            return "[]"  # no milestones, so the sprint view stays
        if args[:2] == ("issue", "list"):
            return json.dumps([issue])
        if args[:2] == ("issue", "edit"):
            edits.append(args)
        return ""

    monkeypatch.setattr(gh_api, "gh", gh)
    sync_project.main()
    assert any("status:backlog" in args for args in edits)
    assert "#9 labels <- project" in capsys.readouterr().out
