"""gh_rest.py: the REST reader every pipeline script uses, because GraphQL is blocked
in cloud sessions."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "gh_rest.py"
spec = importlib.util.spec_from_file_location("gh_rest", SCRIPT)
gh_rest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gh_rest)

REPO = "acme/widgets"


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/acme/widgets",
        "https://github.com/acme/widgets.git",
        "https://github.com/acme/widgets/",
        "git@github.com:acme/widgets.git",
        "ssh://git@github.com/acme/widgets.git",
        "http://local_proxy@127.0.0.1:41055/git/acme/widgets",
    ],
)
def test_repo_from_every_remote_form(url):
    assert gh_rest.repo_from_url(url) == REPO


@pytest.mark.parametrize("url", ["", "/srv/git/widgets.git", "https://gitlab.com/a"])
def test_non_github_remote_is_not_a_repo(url):
    assert gh_rest.repo_from_url(url) is None


def test_current_repo_without_remote_exits_with_the_hint(monkeypatch):
    monkeypatch.setattr(gh_rest, "run", lambda *args: (2, "", "no such remote"))
    with pytest.raises(SystemExit, match="pass --repo owner/name"):
        gh_rest.current_repo()


def test_api_list_flattens_the_pages(monkeypatch):
    sent = []

    def run(*args):
        sent.append(args)
        return 0, json.dumps([[{"n": 1}, {"n": 2}], [{"n": 3}]]), ""

    monkeypatch.setattr(gh_rest, "run", run)
    assert gh_rest.api_list("repos/x/y/labels") == [{"n": 1}, {"n": 2}, {"n": 3}]
    assert sent == [("gh", "api", "--paginate", "--slurp", "repos/x/y/labels")]


def test_api_failure_exits_with_gh_error(monkeypatch):
    monkeypatch.setattr(gh_rest, "run", lambda *args: (1, "", "HTTP 403: blocked"))
    with pytest.raises(SystemExit, match="HTTP 403: blocked"):
        gh_rest.api_list("repos/x/y/issues")


def rest_issue(number, *, blocked_by=0, blocking=0, subs=0, milestone=True, **extra):
    return {
        "number": number,
        "title": f"issue {number}",
        "state": "open",
        "body": f"body {number}",
        "labels": [{"name": "status:explore"}, {"name": "task"}],
        "milestone": {"title": "W1", "number": 1, "state": "open"}
        if milestone
        else None,
        "issue_dependencies_summary": {
            "total_blocked_by": blocked_by,
            "total_blocking": blocking,
        },
        "sub_issues_summary": {"total": subs},
        **extra,
    }


def fake_github(monkeypatch, issues, links=None, pulls=()):
    """Serve `issues` and the per-issue link lists; record every path asked."""
    links = links or {}
    asked = []

    def api_list(path):
        asked.append(path)
        if path.startswith(f"repos/{REPO}/issues?"):
            return issues
        if path.startswith(f"repos/{REPO}/pulls?"):
            return list(pulls)
        return links[path]

    monkeypatch.setattr(gh_rest, "api_list", api_list)
    return asked


def test_issue_becomes_the_graphql_node(monkeypatch):
    fake_github(monkeypatch, [rest_issue(5)])
    [node] = gh_rest.open_issue_nodes(REPO)
    assert node == {
        "number": 5,
        "title": "issue 5",
        "labels": {"nodes": [{"name": "status:explore"}, {"name": "task"}]},
        "milestone": {"title": "W1", "number": 1, "state": "OPEN"},
        "blockedBy": {"nodes": []},
        "blocking": {"nodes": []},
    }


def test_pull_requests_are_left_out(monkeypatch):
    fake_github(monkeypatch, [rest_issue(5), rest_issue(6, pull_request={"url": "x"})])
    assert [n["number"] for n in gh_rest.open_issue_nodes(REPO)] == [5]


def test_issue_without_milestone(monkeypatch):
    fake_github(monkeypatch, [rest_issue(5, milestone=False)])
    assert gh_rest.open_issue_nodes(REPO)[0]["milestone"] is None


def test_links_are_fetched_only_where_the_summary_counts_them(monkeypatch):
    blocker = {"number": 3, "state": "closed"}
    waiter = {"number": 9, "state": "open"}
    asked = fake_github(
        monkeypatch,
        [rest_issue(5, blocked_by=1, blocking=1), rest_issue(6)],
        {
            f"repos/{REPO}/issues/5/dependencies/blocked_by": [blocker],
            f"repos/{REPO}/issues/5/dependencies/blocking": [waiter],
        },
    )
    five, six = gh_rest.open_issue_nodes(REPO)
    assert five["blockedBy"] == {"nodes": [{"number": 3, "state": "CLOSED"}]}
    assert five["blocking"] == {"nodes": [{"number": 9, "state": "OPEN"}]}
    assert six["blockedBy"] == {"nodes": []}
    assert not any("/issues/6/" in path for path in asked)


def test_body_mode_adds_sub_issues_parent_and_closing_prs(monkeypatch):
    fake_github(
        monkeypatch,
        [
            rest_issue(5, subs=1),
            rest_issue(
                7, parent_issue_url=f"https://api.github.com/repos/{REPO}/issues/5"
            ),
        ],
        {f"repos/{REPO}/issues/5/sub_issues": [{"number": 7, "state": "open"}]},
        pulls=[{"body": "Closes #7"}, {"body": "Fixes: #7 and see #5"}],
    )
    five, seven = gh_rest.open_issue_nodes(REPO, with_body=True)
    assert five["body"] == "body 5"
    assert five["subIssues"] == {"nodes": [{"number": 7, "state": "OPEN"}]}
    assert five["parent"] is None
    assert seven["parent"] == {"number": 5}
    assert seven["closedByPullRequestsReferences"] == {"totalCount": 2}
    assert five["closedByPullRequestsReferences"] == {"totalCount": 0}


@pytest.mark.parametrize(
    ("body", "count"),
    [
        ("Closes #12", 1),
        ("resolved #12", 1),
        ("fix #12.", 1),
        ("See #12", 0),
        ("Closes #123", 0),
        ("", 0),
    ],
)
def test_only_a_closing_keyword_links_a_pr(body, count):
    assert gh_rest.closing_pr_count(12, [{"body": body}]) == count
