"""fake_gh.py: the stand-in gh answers from the state file and records every call."""

import json
import os
import subprocess
import sys
from pathlib import Path

import fake_gh
import pytest

HERE = Path(__file__).resolve().parent


@pytest.fixture
def folder(tmp_path, monkeypatch):
    """A state folder with one issue in review and its open PR."""
    state = {
        "repo": "acme/demo",
        "milestones": [{"title": "Sprint 1"}],
        "issues": {
            "12": {
                "title": "ברכה",
                "labels": ["task", "status:in-review"],
                "milestone": "Sprint 1",
                "body": "### מה רוצים\nברכה",
                "blocked_by": [11],
            },
            "11": {"title": "בסיס", "labels": ["task"], "body": ""},
        },
        "pulls": {
            "13": {
                "title": "ברכה",
                "body": "Closes #12",
                "head": "claude/issue-12-x",
                "base": "main",
                "head_sha": "abc123",
            }
        },
    }
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setenv("FAKE_GH_STATE", str(tmp_path))
    return tmp_path


def gh(capsys, *argv):
    """Run one fake gh call; return (exit code, stdout, stderr)."""
    code = fake_gh.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def calls(folder):
    lines = (folder / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_issue_view_reads_the_state(folder, capsys):
    code, out, _ = gh(capsys, "issue", "view", "12", "--json", "title,labels")
    assert code == 0
    assert json.loads(out) == {
        "title": "ברכה",
        "labels": [{"name": "task"}, {"name": "status:in-review"}],
    }


def test_issue_view_jq_prints_raw(folder, capsys):
    code, out, _ = gh(
        capsys,
        "issue",
        "view",
        "12",
        "--json",
        "closedByPullRequestsReferences",
        "--jq",
        ".closedByPullRequestsReferences[].number",
    )
    assert (code, out) == (0, "13\n")


def test_label_change_is_saved_and_written_for_graders(folder, capsys):
    code, _, _ = gh(
        capsys,
        "issue",
        "edit",
        "12",
        "--add-label",
        "status:done",
        "--remove-label",
        "status:in-review",
    )
    assert code == 0
    labels = (folder / "issues" / "12.labels").read_text(encoding="utf-8")
    assert labels == "status:done\ntask\n"


def test_unknown_label_fails(folder, capsys):
    code, _, err = gh(capsys, "issue", "edit", "12", "--add-label", "nope")
    assert code == 1
    assert "not found" in err


def test_body_file_replaces_the_body(folder, capsys, tmp_path):
    body = tmp_path / "body.md"
    body.write_text("גוף חדש", encoding="utf-8")
    assert gh(capsys, "issue", "edit", "12", "--body-file", str(body))[0] == 0
    assert (folder / "issues" / "12.body.md").read_text(encoding="utf-8") == "גוף חדש"


def test_comment_is_recorded(folder, capsys):
    assert gh(capsys, "issue", "comment", "12", "--body", "מוכן")[0] == 0
    text = (folder / "issues" / "12.comments.md").read_text(encoding="utf-8")
    assert text == "מוכן"


def test_merge_is_recorded_and_closes_the_issue(folder, capsys):
    assert gh(capsys, "pr", "merge", "13", "--squash")[0] == 0
    assert (folder / "pulls" / "13.state").read_text() == "merged\n"
    assert (folder / "issues" / "12.state").read_text() == "closed\n"
    assert calls(folder)[-1]["argv"] == ["pr", "merge", "13", "--squash"]


def test_merge_twice_fails(folder, capsys):
    gh(capsys, "pr", "merge", "13", "--squash")
    assert gh(capsys, "pr", "merge", "13", "--squash")[0] == 1


def test_pr_create_takes_the_next_number(folder, capsys):
    code, out, _ = gh(
        capsys,
        "pr",
        "create",
        "--title",
        "t",
        "--body",
        "Closes #11",
        "--head",
        "claude/issue-11-y",
    )
    assert (code, out) == (0, "https://github.com/acme/demo/pull/14\n")
    assert (folder / "pulls" / "14.body.md").read_text() == "Closes #11"


def test_pr_checks_fail_with_exit_1(folder, capsys):
    data = json.loads((folder / "state.json").read_text())
    data["pulls"]["13"]["checks"] = "failure"
    (folder / "state.json").write_text(json.dumps(data))
    code, out, _ = gh(capsys, "pr", "checks", "13", "--watch")
    assert code == 1
    assert "fail" in out


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["api", "repos/{owner}/{repo}/issues/12", "--jq", ".state"], "open\n"),
        (
            ["api", "repos/acme/demo/pulls/13", "--jq", ".head.ref"],
            "claude/issue-12-x\n",
        ),
        (
            [
                "api",
                "repos/acme/demo/issues/12/dependencies/blocked_by",
                "--jq",
                ".[].number",
            ],
            "11\n",
        ),
        (
            [
                "api",
                "repos/acme/demo/issues/11/dependencies/blocking",
                "--jq",
                ".[].number",
            ],
            "12\n",
        ),
        (
            ["api", "repos/acme/demo/issues?state=open&labels=task", "--jq", "length"],
            "2\n",
        ),
        (["api", "repos/acme/demo", "--jq", ".default_branch"], "main\n"),
    ],
)
def test_rest_reads(folder, capsys, argv, expected):
    assert gh(capsys, *argv)[:2] == (0, expected)


def test_rest_label_add_and_remove(folder, capsys):
    path = "repos/acme/demo/issues/12/labels"
    assert gh(capsys, "api", "-X", "POST", path, "-f", "labels[]=status:done")[0] == 0
    assert gh(capsys, "api", "-X", "DELETE", f"{path}/status:in-review")[0] == 0
    assert (folder / "issues" / "12.labels").read_text() == "status:done\ntask\n"


def test_rest_merge(folder, capsys):
    assert gh(capsys, "api", "-X", "PUT", "repos/acme/demo/pulls/13/merge")[0] == 0
    assert (folder / "pulls" / "13.state").read_text() == "merged\n"


def test_other_repo_is_404(folder, capsys):
    code, _, err = gh(capsys, "api", "repos/acme/.github/contents/x.yml")
    assert code == 1
    assert "HTTP 404" in err


def test_graphql_issue_query(folder, capsys):
    code, out, _ = gh(
        capsys,
        "api",
        "graphql",
        "-f",
        "query=query{repository{issue(number: 12){blockedBy{nodes{number}}}}}",
        "--jq",
        ".data.repository.issue.blockedBy.nodes[].number",
    )
    assert (code, out) == (0, "11\n")


@pytest.mark.parametrize(
    "argv",
    [
        ["release", "list"],
        ["issue", "transfer", "12"],
        ["api", "repos/acme/demo/hooks"],
    ],
)
def test_unknown_command_is_logged_and_fails(folder, capsys, argv):
    code, _, err = gh(capsys, *argv)
    assert code == 1
    assert "unsupported" in err
    assert calls(folder)[-1]["unsupported"] is True


def test_no_state_fails(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("FAKE_GH_STATE", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert fake_gh.main(["issue", "view", "12"]) == 1
    assert ".fake-gh-state" in capsys.readouterr().err


def test_the_gh_wrapper_runs_it(folder, tmp_path):
    """The shell wrapper run.py puts on PATH, with its exit code."""
    fake = tmp_path / "fake"
    (fake / "bin").mkdir(parents=True)
    for module in HERE.glob("fake_gh*.py"):
        (fake / module.name).write_text(module.read_text("utf-8"), "utf-8")
    wrapper = fake / "bin" / "gh"
    wrapper.write_text((HERE / "bin" / "gh").read_text("utf-8"), "utf-8")
    wrapper.chmod(0o755)
    env = dict(os.environ, FAKE_GH_STATE=str(folder))
    env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{env['PATH']}"
    ok = subprocess.run(
        [str(wrapper), "pr", "view", "13", "--json", "state"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert (ok.returncode, json.loads(ok.stdout)) == (0, {"state": "OPEN"})
    bad = subprocess.run(
        [str(wrapper), "nope"], capture_output=True, text=True, env=env, check=False
    )
    assert bad.returncode == 1
