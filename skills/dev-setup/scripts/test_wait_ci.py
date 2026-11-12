"""wait_ci.py: waits for the CI of one pushed commit and prints the result."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("wait_ci", HERE / "wait_ci.py")
wait_ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wait_ci)


def run(name, status="completed", conclusion="success"):
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion if status == "completed" else None,
        "html_url": f"https://github.com/o/r/runs/{name}",
    }


class FakeClock:
    """A clock that moves only when the script sleeps."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def wait(rounds, interval=30, timeout=1800):
    """Run wait() over a list of check-run lists, one per round (the last repeats)."""
    clock, calls = FakeClock(), []

    def read_runs():
        calls.append(1)
        return rounds[min(len(calls), len(rounds)) - 1]

    lines = wait_ci.wait(read_runs, interval, timeout, clock.sleep, clock)
    return lines, len(calls)


def test_green_checks_print_success():
    assert wait([[run("tests"), run("lint", conclusion="skipped")]]) == (
        ["success"],
        1,
    )


def test_red_checks_print_failure_with_name_and_link():
    lines, _ = wait([[run("tests", conclusion="failure"), run("lint")]])
    assert lines == ["failure", "tests failure https://github.com/o/r/runs/tests"]


def test_pending_then_green_in_the_second_round():
    pending = [run("tests", status="in_progress")]
    assert wait([pending, [run("tests")]]) == (["success"], 2)


def test_checks_that_never_finish_time_out_pending():
    lines, calls = wait([[run("tests", status="queued")]], interval=30, timeout=90)
    assert lines == ["timeout pending"]
    assert calls == 4


def test_no_check_ever_showing_up_times_out_not_started():
    lines, _ = wait([[]], interval=30, timeout=60)
    assert lines == ["timeout not-started"]


def workflows(tmp_path, **files):
    folder = tmp_path / ".github" / "workflows"
    folder.mkdir(parents=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("on:\n  pull_request:\n  push:\n    branches: [main]\n", True),
        ("on: [push, pull_request]\n", True),
        ("on: pull_request_target\n", True),
        ('"on":\n  pull_request:\n', True),
        ("on:\n  issues:\n    types: [labeled]\n", False),
        ("on:\n  push:\njobs:\n  pull_request:\n    runs-on: x\n", False),
    ],
)
def test_pull_request_workflow_is_found_in_the_on_key(tmp_path, text, expected):
    root = workflows(tmp_path, **{"ci.yml": text})
    assert wait_ci.has_pr_workflow(root) is expected


def test_no_workflows_folder_means_no_ci(tmp_path):
    assert wait_ci.has_pr_workflow(tmp_path) is False


def test_no_pull_request_workflow_prints_none_without_reading_github(
    tmp_path, monkeypatch, capsys
):
    root = workflows(tmp_path, **{"sync.yml": "on:\n  issues:\n"})
    monkeypatch.setattr(wait_ci, "api", lambda path: pytest.fail("read GitHub"))
    wait_ci.main(["--sha", "abc1234", "--root", str(root), "--repo", "o/r"])
    assert capsys.readouterr().out == "none\n"


def test_main_reads_the_check_runs_of_the_given_sha(tmp_path, monkeypatch, capsys):
    root = workflows(tmp_path, **{"tests.yml": "on:\n  pull_request:\n"})
    paths = []

    def api(path):
        paths.append(path)
        return {"check_runs": [run("tests")]}

    monkeypatch.setattr(wait_ci, "api", api)
    wait_ci.main(["--sha", "ABC1234", "--root", str(root), "--repo", "o/r"])
    assert capsys.readouterr().out == "success\n"
    assert paths == ["repos/o/r/commits/abc1234/check-runs?per_page=100"]


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--sha", "not-a-sha"],
        ["--sha", "abc12"],
        ["--sha", "abc1234", "--timeout", "0"],
    ],
)
def test_bad_input_exits_2(argv):
    with pytest.raises(SystemExit) as raised:
        wait_ci.main(argv)
    assert raised.value.code == 2


def test_running_the_file_with_bad_input_exits_2():
    result = subprocess.run(
        [sys.executable, str(HERE / "wait_ci.py"), "--sha", "zzz"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "not a commit sha" in result.stderr
