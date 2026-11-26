"""billing_flag.py: the account-wide flag that says GitHub billing is blocked."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import billing_flag  # noqa: E402
import pipeline_shas  # noqa: E402

URL = "https://github.com/o/r/actions/runs/1/job/2"


def sh(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def remote(tmp_path, monkeypatch):
    """A bare repo with a main, standing in for claude-config on GitHub."""
    work, bare = tmp_path / "work", tmp_path / "remote.git"
    work.mkdir()
    sh(work, "init", "-q", "-b", "main")
    sh(work, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q",
       "--allow-empty", "-m", "init")  # fmt: skip
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)
    monkeypatch.setattr(pipeline_shas, "PIPELINE_URL", bare.as_uri())
    return bare


@pytest.fixture
def cache(tmp_path):
    return tmp_path / "cache.git"


def on_github(bare):
    """The flag file on the remote's branch, as JSON."""
    return json.loads(sh(bare, "show", f"{billing_flag.REF}:{billing_flag.FILE}"))


def test_no_branch_is_off(remote, cache):
    assert billing_flag.read(cache) == billing_flag.OFF
    assert billing_flag.current(cache) is None


def test_on_by_hand_then_status(remote, cache):
    flag = billing_flag.turn_on(cache, "manual", None, lambda: "2026-11-15T10:00:00")
    assert billing_flag.status_line(flag) == "on 2026-11-15T10:00:00 manual -"
    assert on_github(remote)["blocked"] is True
    assert billing_flag.current(cache)["notice"] == (
        "החיוב ב-GitHub חסום מאז 2026-11-15 (הודלק ביד). "
        'כשהחיוב מסודר, תבקש "תכבה את דגל החיוב".'
    )


def test_on_when_already_on_keeps_since(remote, cache):
    billing_flag.turn_on(cache, "auto", URL, lambda: "2026-11-01T00:00:00")
    flag = billing_flag.turn_on(cache, "manual", None, lambda: "2026-11-15T00:00:00")
    assert flag["since"] == "2026-11-01T00:00:00"
    assert flag["source"] == "auto"
    assert len(sh(remote, "log", "--format=%H", billing_flag.REF).split()) == 1


def test_off_is_a_new_commit_on_top(remote, cache):
    billing_flag.turn_on(cache, "auto", URL, lambda: "2026-11-01T00:00:00")
    assert "נדלק לבד בריצה " + URL in billing_flag.current(cache)["notice"]
    billing_flag.turn_off(cache)
    assert on_github(remote)["blocked"] is False
    assert billing_flag.current(cache) is None
    assert len(sh(remote, "log", "--format=%H", billing_flag.REF).split()) == 2


def test_off_with_no_branch_writes_nothing(remote, cache):
    billing_flag.turn_off(cache)
    assert sh(remote, "branch", "--list", billing_flag.BRANCH) == ""


def test_a_push_that_fails_is_not_written(remote, cache):
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho denied >&2\nexit 1\n")
    hook.chmod(0o755)
    lines = billing_flag.billing_lines(URL, cache, lambda: "2026-11-15T00:00:00")
    assert lines[0] == f"billing {URL}"
    assert lines[1].startswith("not-written ")
    assert "denied" in lines[1]


def test_git_that_does_not_answer_is_unknown(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pipeline_shas, "PIPELINE_URL", (tmp_path / "none").as_uri())
    monkeypatch.setattr(billing_flag, "CACHE", tmp_path / "cache.git")
    assert billing_flag.main(["status"]) == 0
    out = capsys.readouterr()
    assert out.out == "unknown\n"
    assert "billing flag was not read" in out.err
    assert billing_flag.current(tmp_path / "cache.git") is None


@pytest.mark.parametrize(
    ("url", "expected"),
    [(URL, f"billing {URL}\n"), (None, "not-billing\n")],
)
def test_check_prints_billing_or_not(url, expected, monkeypatch, capsys):
    monkeypatch.setattr(billing_flag, "api_list", lambda path, key: [])
    monkeypatch.setattr(billing_flag, "billing_run", lambda repo, runs: url)
    monkeypatch.setattr(billing_flag, "turn_on", lambda *args: {})
    assert billing_flag.main(["check", "--sha", "abc1234", "--repo", "o/r"]) == 0
    assert capsys.readouterr().out == expected


def test_script_on_and_off_with_exit_codes(remote, tmp_path):
    git_dir = str(Path(shutil.which("git")).parent)
    env = {
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),  # Windows reads the home from here
        "PATH": os.pathsep.join(["/usr/bin", "/bin", git_dir]),
    }
    if "SYSTEMROOT" in os.environ:  # Python on Windows cannot start without it
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    script = HERE / "billing_flag.py"
    # The script's own PIPELINE_URL is GitHub's; a wrapper points it at the remote.
    runner = tmp_path / "run.py"
    runner.write_text(
        "import sys, runpy\n"
        f"sys.path.insert(0, {str(HERE)!r})\n"
        "import pipeline_shas\n"
        f"pipeline_shas.PIPELINE_URL = {remote.as_uri()!r}\n"
        f"sys.argv = [{str(script)!r}, *sys.argv[1:]]\n"
        f"runpy.run_path({str(script)!r}, run_name='__main__')\n"
    )

    def run(*args):
        return subprocess.run(
            [sys.executable, str(runner), *args],
            capture_output=True,
            text=True,
            env=env,
        )

    turned_on = run("on", "--manual")
    assert turned_on.returncode == 0
    assert turned_on.stdout.startswith("on ")
    assert run("status").stdout.startswith("on ")
    assert run("off").stdout == "off\n"
    assert run("status").stdout == "off\n"
    assert run("on").returncode == 2


def test_a_rejected_push_after_another_session_turned_it_on_is_a_success(
    remote, cache, monkeypatch
):
    real_write = billing_flag.write

    def other_session_first(cache_path, flag, message):
        real_write(cache_path, flag | {"since": "2026-11-01T00:00:00"}, "other")
        raise billing_flag.NotWrittenError("rejected: not a fast-forward")

    monkeypatch.setattr(billing_flag, "write", other_session_first)
    flag = billing_flag.turn_on(cache, "auto", URL, lambda: "2026-11-15T00:00:00")
    assert flag["since"] == "2026-11-01T00:00:00"


def deny_pushes(remote):
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho denied >&2\nexit 1\n")
    hook.chmod(0o755)


@pytest.mark.parametrize("argv", [["on", "--manual"], ["off"]])
def test_a_failed_write_exits_1_with_not_written(
    argv, remote, cache, monkeypatch, capsys
):
    monkeypatch.setattr(billing_flag, "CACHE", cache)
    if argv == ["off"]:
        billing_flag.turn_on(cache, "manual", None, lambda: "2026-11-15T00:00:00")
    deny_pushes(remote)
    assert billing_flag.main(argv) == 1
    assert capsys.readouterr().out.startswith("not-written ")


def test_check_exits_1_when_the_flag_was_not_written(
    remote, cache, monkeypatch, capsys
):
    monkeypatch.setattr(billing_flag, "CACHE", cache)
    monkeypatch.setattr(billing_flag, "api_list", lambda path, key: [])
    monkeypatch.setattr(billing_flag, "billing_run", lambda repo, runs: URL)
    deny_pushes(remote)
    assert billing_flag.main(["check", "--sha", "abc1234", "--repo", "o/r"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"billing {URL}" and out[1].startswith("not-written ")


def broken_name_branch(bare):
    """The branch as a Windows write left it: the file named `billing.json\\r`."""
    flag = {"blocked": True, "since": "2026-11-18T08:00:00", "source": "auto"}
    content = json.dumps(flag | {"run": URL}) + "\r\n"
    blob = sh_input(bare, content.encode(), "hash-object", "-w", "--stdin")
    entry = f"100644 blob {blob}\tbilling.json\r\n".encode()
    tree = sh_input(bare, entry, "mktree")
    author = ("-c", "user.name=t", "-c", "user.email=t@e")
    commit = sh(bare, *author, "commit-tree", tree, "-m", "billing flag on (auto)")
    sh(bare, "update-ref", billing_flag.REF, commit.strip())


def sh_input(repo, data, *args):
    """git with `data` as raw bytes on stdin; its stdout, stripped."""
    done = subprocess.run(
        ["git", "-C", str(repo), *args], input=data, check=True, capture_output=True
    )
    return done.stdout.decode().strip()


def test_a_name_ending_in_cr_is_read(remote, cache):
    broken_name_branch(remote)
    flag = billing_flag.read(cache)
    assert billing_flag.status_line(flag) == f"on 2026-11-18T08:00:00 auto {URL}"


def test_the_next_write_restores_the_name(remote, cache):
    broken_name_branch(remote)
    billing_flag.turn_off(cache)
    names = sh(remote, "ls-tree", "-z", "--name-only", billing_flag.REF)
    assert names == f"{billing_flag.FILE}\0"
    assert on_github(remote) == billing_flag.OFF


def test_mktree_gets_no_line_break(remote, cache, monkeypatch):
    """Windows text mode would turn a "\\n" into "\\r\\n" inside the name."""
    seen = {}
    real_git = billing_flag.git

    def recording(*args, stdin=None):
        if "mktree" in args:
            seen["stdin"] = stdin
        return real_git(*args, stdin=stdin)

    monkeypatch.setattr(billing_flag, "git", recording)
    billing_flag.turn_on(cache, "manual", None, lambda: "2026-11-15T10:00:00")
    assert "\n" not in seen["stdin"]
    assert on_github(remote)["blocked"] is True
