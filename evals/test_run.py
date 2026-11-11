"""run.py and summary.py: which cases run, the command they run with, and the report.

No call to a model: the command is checked with --dry-run, and the report from sample
results.
"""

import json
import subprocess
from pathlib import Path

import pytest
import run
from summary import summarize


@pytest.mark.parametrize(
    ("files", "tags"),
    [
        (["skills/dev-ship/SKILL.md"], ["dev-ship"]),
        (["skills/dev-plan/SKILL.md", "README.md"], ["dev-plan"]),
        (["skills/dev-setup/reference/pipeline.md"], list(run.SKILLS)),
        (["evals/fake_gh.py"], list(run.SKILLS)),
        (["hooks/x.py", "rules/git.md"], []),
        (["skills/dev-issue/SKILL.md"], []),
        ([], []),
    ],
)
def test_tags_follow_the_changed_files(files, tags):
    assert run.tags_for(files) == tags


@pytest.fixture
def ready(monkeypatch, tmp_path, capsys):
    """main() with the tools present and any work folder allowed; returns a runner."""
    monkeypatch.setattr(run, "missing_tools", lambda: [])
    monkeypatch.setattr(run, "unreachable", lambda folder: None)
    monkeypatch.setattr(run, "changed_files", lambda base: ["skills/dev-ship/SKILL.md"])

    def main(*argv):
        code = run.main(["--work-dir", str(tmp_path), *argv])
        return code, capsys.readouterr().out

    return main


def test_dry_run_prints_the_command(ready):
    code, out = ready("--dry-run")
    assert code == 0
    command = out.split()
    assert command[:3] == ["claude", "plugin", "eval"]
    assert command[command.index("--runs") + 1] == "2"
    assert command[command.index("--max-cost-usd") + 1] == "10.0"
    assert command[command.index("--tag") + 1 :] == ["dev-ship"]
    assert "--model" not in command
    for flag in ("--scaffold", "--trust-plugin", "--no-publish"):
        assert flag in command


def test_model_and_ceiling_are_passed(ready):
    _, out = ready("--dry-run", "--model", "claude-opus-5-5", "--max-cost-usd", "3")
    command = out.split()
    assert command[command.index("--model") + 1] == "claude-opus-5-5"
    assert command[command.index("--max-cost-usd") + 1] == "3.0"


def test_holdout_runs_every_held_out_case(ready):
    _, out = ready("--dry-run", "--holdout")
    assert "--tag" not in out.split()


def test_all_runs_every_skill(ready):
    _, out = ready("--dry-run", "--all")
    command = out.split()
    assert command[command.index("--tag") + 1 :] == list(run.SKILLS)


def test_no_covered_skill_runs_nothing(ready, monkeypatch):
    monkeypatch.setattr(run, "changed_files", lambda base: ["hooks/x.py"])
    code, out = ready()
    assert code == 0
    assert "לא הורצו" in out


def test_missing_tools_exit_2(ready, monkeypatch):
    monkeypatch.setattr(run, "missing_tools", lambda: ["bwrap", "socat"])
    code, out = ready()
    assert code == 2
    assert "לא הורץ: חסר bwrap, socat" in out


@pytest.mark.parametrize(
    ("folder", "blocked"),
    [("/tmp/x", True), ("/var/tmp/x", True), (str(Path.home() / "x"), True)],
)
def test_work_folder_under_tmp_or_home_is_refused(folder, blocked):
    assert (run.unreachable(Path(folder)) is not None) == blocked


def test_work_folder_elsewhere_is_allowed(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    assert run.unreachable(Path("/srv/repo/evals/results")) is None


def test_build_plugin(tmp_path):
    plugin = run.build_plugin(tmp_path, holdout=False)
    manifest = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == run.PLUGIN_NAME
    assert (plugin / "skills" / "dev-ship" / "SKILL.md").exists()
    assert (plugin / "evals" / "dev-ship-merge-on-request" / "prompt.md").exists()
    assert (plugin / "evals" / "scaffold.sh").exists()
    assert (plugin / "claude-home" / "rules" / "git.md").exists()
    assert plugin.parent != tmp_path  # the sandbox denies reads in the plugin's parent


def test_build_plugin_holdout(tmp_path):
    plugin = run.build_plugin(tmp_path, holdout=True)
    names = {p.name for p in (plugin / "evals").iterdir()}
    assert "dev-ship-merge-on-request" not in names
    assert "dev-ship-ready-question" in names


def case(name, score, graders=(), case_dir="", cost=0.5, error=None):
    runs = [{"score": score, "costUsd": cost, "error": error, "graders": list(graders)}]
    return {
        "name": name,
        "dir": case_dir,
        "aggregates": {"score": score},
        "arms": {"with": runs},
    }


def test_summary_one_line_per_skill():
    result = {
        "suite": {"threshold": 1},
        "costUsd": 1.5,
        "cases": [
            case("dev-ship-merge", 1, cost=0.75),
            case("dev-ship-status", 1, cost=0.25),
            case("dev-plan-x", 1, cost=0.5),
        ],
    }
    lines, failed = summarize(result, run.SKILLS)
    assert lines[:2] == [
        "dev-ship: 2 מתוך 2 עברו, עלות 1.00 דולר",
        "dev-plan: 1 מתוך 1 עברו, עלות 0.50 דולר",
    ]
    assert not failed


def test_summary_failure_names_the_rule(tmp_path):
    """The result's dir is relative to the plugin, as claude plugin eval writes it."""
    graders = tmp_path / "evals" / "dev-ship-status" / "graders"
    graders.mkdir(parents=True)
    (graders / "no-merge.md").write_text(
        "---\ntype: regex\n---\nנקרא מיזוג בלי בקשה.\n"
    )
    failing = {"name": "no-merge", "passed": False, "scored": True, "explanation": "x"}
    result = {"cases": [case("dev-ship-status", 0, [failing], "evals/dev-ship-status")]}
    lines, failed = summarize(result, run.SKILLS, tmp_path)
    assert failed
    assert "נכשל: dev-ship-status" in lines
    assert "  נקרא מיזוג בלי בקשה." in lines


def test_summary_cost_ceiling_is_not_a_failure():
    result = {
        "partial": True,
        "partialReason": "cost_ceiling",
        "cases": [case("dev-ship-a", 1), {"name": "dev-code-b", "arms": {"with": []}}],
    }
    lines, failed = summarize(result, run.SKILLS)
    assert not failed
    assert "נעצר בתקרת העלות. לא הספיקו לרוץ: dev-code-b." in lines
    assert "dev-code: 0 מתוך 0 עברו, עלות 0.00 דולר" in lines


def test_missing_base_is_not_run(ready, monkeypatch):
    def missing(base):
        raise run.BaseMissingError(base)

    monkeypatch.setattr(run, "changed_files", missing)
    code, out = ready()
    assert code == 2
    assert "לא הורץ: אין origin/main" in out


def test_changed_files_unknown_base_raises():
    with pytest.raises(run.BaseMissingError):
        run.changed_files("no-such-ref-183")


def fake_eval(monkeypatch, exit_code, result=None):
    """A stand-in `claude plugin eval`: writes result.json, exits with exit_code."""

    def fake(command, **kwargs):
        if result is not None:
            target = Path(command[command.index("--json") + 1])
            target.write_text(json.dumps(result), encoding="utf-8")
        return subprocess.CompletedProcess(command, exit_code)

    monkeypatch.setattr(run.subprocess, "run", fake)


@pytest.mark.parametrize(
    ("exit_code", "score", "expected"),
    [(0, 1, 0), (1, 0, 1), (2, 1, 2), (2, 0, 1)],
)
def test_exit_code_after_the_run(ready, monkeypatch, exit_code, score, expected):
    """A failed case is 1 even when the run stopped (2), say at the cost ceiling."""
    fake_eval(monkeypatch, exit_code, {"cases": [case("dev-ship-a", score)]})
    assert ready()[0] == expected


def test_no_result_is_not_run(ready, monkeypatch):
    fake_eval(monkeypatch, 1)
    code, out = ready()
    assert code == 2
    assert "בלי תוצאה" in out
