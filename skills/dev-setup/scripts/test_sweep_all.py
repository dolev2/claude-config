"""The central scheduled board sync, run from the public dolev2/.github (#46).

Its log is public, so the main thing guarded here is that no repo name or issue
number reaches it, not even when a repo fails.
"""

import importlib.util
import subprocess
from pathlib import Path

ACTION = Path(__file__).resolve().parents[1] / "actions" / "project-sync"
REPOS = ["dolev2/secret-crm", "dolev2/no-board", "dolev2/hidden-plan"]
BOARDS = {
    "dolev2/secret-crm": {"PROJECT_NUMBER": "1", "SYNC_MARKER": "crm-sync"},
    "dolev2/no-board": {},
    "dolev2/hidden-plan": {"PROJECT_NUMBER": "4", "SYNC_MARKER": "plan-sync"},
}


def load_sweep():
    spec = importlib.util.spec_from_file_location("sweep_all", ACTION / "sweep_all.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def done(code, stdout="", stderr=""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


def fake(monkeypatch, results):
    """A sweep whose repos are REPOS and whose sync returns results[repo]."""
    sweep = load_sweep()
    ran = []
    monkeypatch.setattr(sweep, "list_repos", lambda owner: list(REPOS))
    monkeypatch.setattr(sweep, "repo_variables", lambda repo: BOARDS[repo])
    monkeypatch.setattr(
        sweep, "run_sync", lambda repo, variables: ran.append(repo) or results[repo]
    )
    return sweep, ran


def test_a_repo_without_a_board_is_skipped(monkeypatch, capsys):
    sweep, ran = fake(
        monkeypatch,
        {
            "dolev2/secret-crm": done(0, "updated issues: 2\n"),
            "dolev2/hidden-plan": done(0, "updated issues: 1\n"),
        },
    )
    assert sweep.main(["--owner", "dolev2"]) == 0
    assert ran == ["dolev2/secret-crm", "dolev2/hidden-plan"]
    out = capsys.readouterr().out
    assert "repos: 3, with a board: 2, issues updated: 3, failed: 0" in out


def test_a_failed_repo_does_not_stop_the_rest_and_names_nothing(monkeypatch, capsys):
    sweep, ran = fake(
        monkeypatch,
        {
            "dolev2/secret-crm": done(
                1, "#12 labels <- project", "gh: dolev2/secret-crm not found"
            ),
            "dolev2/hidden-plan": done(0, "updated issues: 1\n"),
        },
    )
    assert sweep.main(["--owner", "dolev2"]) == 1
    assert ran == ["dolev2/secret-crm", "dolev2/hidden-plan"]
    out = capsys.readouterr().out
    assert "repo 1 of 3 failed" in out
    assert "failed: 1" in out
    assert "secret" not in out and "hidden" not in out and "#" not in out


def test_unreadable_variables_count_as_a_failure_without_the_message(
    monkeypatch, capsys
):
    sweep, _ = fake(monkeypatch, {"dolev2/hidden-plan": done(0, "updated issues: 0")})

    def variables(repo):
        if repo == "dolev2/secret-crm":
            raise RuntimeError("HTTP 404: dolev2/secret-crm")
        return BOARDS[repo]

    monkeypatch.setattr(sweep, "repo_variables", variables)
    assert sweep.main(["--owner", "dolev2"]) == 1
    out = capsys.readouterr().out
    assert "repo 1 of 3 failed" in out and "secret" not in out


def test_a_sync_without_its_summary_line_is_a_failure(monkeypatch, capsys):
    # A sync_project.py from before quiet mode would print issue lines instead.
    sweep, _ = fake(
        monkeypatch,
        {
            "dolev2/secret-crm": done(0, ""),
            "dolev2/hidden-plan": done(0, "updated issues: 0"),
        },
    )
    assert sweep.main(["--owner", "dolev2"]) == 1
    assert "failed: 1" in capsys.readouterr().out


def test_verbose_names_the_repo_and_its_error(monkeypatch, capsys):
    sweep, _ = fake(
        monkeypatch,
        {
            "dolev2/secret-crm": done(1, "", "boom"),
            "dolev2/hidden-plan": done(0, "updated issues: 0"),
        },
    )
    sweep.main(["--owner", "dolev2", "--verbose"])
    out = capsys.readouterr().out
    assert "dolev2/secret-crm" in out and "boom" in out


def test_each_repo_runs_a_quiet_full_sweep(monkeypatch):
    sweep = load_sweep()
    seen = {}

    def run(cmd, env, **kwargs):
        seen.update(cmd=cmd, env=env)
        return done(0, "updated issues: 0")

    monkeypatch.setenv("ISSUE_NUMBER", "7")
    monkeypatch.setattr(sweep.subprocess, "run", run)
    sweep.run_sync("dolev2/secret-crm", BOARDS["dolev2/secret-crm"])
    assert seen["cmd"][-1].endswith("sync_project.py")
    env = seen["env"]
    assert env["GITHUB_REPOSITORY"] == "dolev2/secret-crm"
    assert env["PROJECT_NUMBER"] == "1" and env["SYNC_MARKER"] == "crm-sync"
    assert env["SYNC_QUIET"] == "1"
    assert "ISSUE_NUMBER" not in env
