"""watch_children.py: wakes the orchestrator when a child's issue moves on GitHub."""

import importlib.util
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location(
    "watch_children", HERE / "watch_children.py"
)
watch_children = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch_children)

SINCE = datetime.fromisoformat("2026-11-08T15:00:00Z")


def issue(status):
    return {"labels": [{"name": "task"}, {"name": f"status:{status}"}]}


def comment(n, created):
    return {
        "html_url": f"https://github.com/o/r/issues/1#issuecomment-{n}",
        "created_at": created,
    }


def changes(expected, issues, comments=None):
    comments = comments or {}
    return watch_children.changes(
        expected, SINCE, issues.__getitem__, lambda n: comments.get(n, [])
    )


def test_status_that_moved_is_reported():
    lines = changes({184: "explore"}, {184: issue("waiting-approval")})
    assert lines == ["#184 status explore -> waiting-approval"]


def test_unchanged_status_and_no_comments_is_quiet():
    assert (
        changes(
            {184: "explore", 181: "in-review"},
            {
                184: issue("explore"),
                181: issue("in-review"),
            },
        )
        == []
    )


def test_issue_without_status_label_reads_none():
    lines = changes({184: "explore"}, {184: {"labels": []}})
    assert lines == ["#184 status explore -> none"]


def test_only_comments_created_after_since_count():
    old = comment(1, "2026-11-08T14:59:59Z")
    new = comment(2, "2026-11-08T15:00:01Z")
    lines = changes(
        {181: "ready-to-execute"},
        {181: issue("ready-to-execute")},
        {181: [old, new]},
    )
    assert lines == [f"#181 comment {new['html_url']}"]


class Clock:
    """A fake clock that moves only when the watch sleeps."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def __call__(self):
        return self.now


def test_change_already_there_at_start_exits_at_once():
    clock = Clock()
    found = watch_children.watch(lambda: ["#1 x"], 60, 1500, clock.sleep, clock)
    assert found == ["#1 x"]
    assert clock.sleeps == []


def test_change_on_a_later_round_is_returned():
    rounds = iter([[], [], ["#1 comment u"]])
    clock = Clock()
    found = watch_children.watch(lambda: next(rounds), 60, 1500, clock.sleep, clock)
    assert found == ["#1 comment u"]
    assert clock.sleeps == [60, 60]


def test_timeout_without_change():
    clock = Clock()
    found = watch_children.watch(lambda: [], 60, 150, clock.sleep, clock)
    assert found == ["timeout"]
    assert clock.now <= 150


@pytest.mark.parametrize("text", ["", "184", "x=explore", "184=", "184=explore,=x"])
def test_bad_expect_is_rejected(text):
    with pytest.raises(watch_children.argparse.ArgumentTypeError):
        watch_children.expect_map(text)


def test_expect_reads_several_issues():
    assert watch_children.expect_map("184=explore, 181=ready-to-execute") == {
        184: "explore",
        181: "ready-to-execute",
    }


@pytest.mark.parametrize("text", ["yesterday", "2026-11-08T15:00:00"])
def test_bad_since_is_rejected(text):
    with pytest.raises(watch_children.argparse.ArgumentTypeError):
        watch_children.iso_time(text)


def test_main_prints_change_and_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(watch_children, "api", lambda path: issue("in-review"))
    monkeypatch.setattr(watch_children, "api_list", lambda path: [])
    watch_children.main(
        [
            "--repo",
            "o/r",
            "--expect",
            "184=ready-to-execute",
            "--since",
            "2026-11-08T15:00:00Z",
        ]
    )
    assert (
        capsys.readouterr().out.strip() == "#184 status ready-to-execute -> in-review"
    )


def test_main_queries_comments_since_in_utc(monkeypatch):
    paths = []
    monkeypatch.setattr(watch_children, "api", lambda path: issue("explore"))
    monkeypatch.setattr(
        watch_children, "api_list", lambda path: paths.append(path) or []
    )
    monkeypatch.setattr(watch_children.time, "sleep", lambda s: None)
    watch_children.main(
        [
            "--repo",
            "o/r",
            "--expect",
            "7=explore",
            "--since",
            "2026-11-08T17:00:00+02:00",
            "--interval",
            "1",
            "--timeout",
            "1",
        ]
    )
    assert paths == [
        "repos/o/r/issues/7/comments?since=2026-11-08T15:00:00Z&per_page=100"
    ]


def test_running_with_bad_input_exits_2():
    result = subprocess.run(
        [
            sys.executable,
            str(HERE / "watch_children.py"),
            "--expect",
            "nope",
            "--since",
            "2026-11-08T15:00:00Z",
            "--repo",
            "o/r",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "not N=status" in result.stderr
