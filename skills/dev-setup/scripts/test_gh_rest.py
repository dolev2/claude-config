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


def flaky_gh(monkeypatch, failures):
    """`gh` that fails with each stderr in `failures`, then succeeds; counts calls."""
    calls = []
    monkeypatch.setattr(gh_rest.time, "sleep", lambda seconds: calls.append(seconds))

    def run(*args):
        calls.append(args)
        tries = [c for c in calls if isinstance(c, tuple)]
        if len(tries) <= len(failures):
            return 1, "", failures[len(tries) - 1]
        return 0, '{"ok": true}', ""

    monkeypatch.setattr(gh_rest, "run", run)
    return calls


@pytest.mark.parametrize(
    "stderr",
    [
        "HTTP 502: Bad Gateway",
        "HTTP 503: Service Unavailable",
        "read tcp 1.2.3.4:443: connection reset by peer",
        "net/http: TLS handshake timeout",
        "Post https://api.github.com: i/o timeout",
    ],
)
def test_a_transient_failure_is_tried_again(monkeypatch, stderr):
    calls = flaky_gh(monkeypatch, [stderr])
    assert gh_rest.api("repos/x/y") == {"ok": True}
    assert calls == [("gh", "api", "repos/x/y"), 2, ("gh", "api", "repos/x/y")]


def test_three_transient_failures_exit_with_the_last_error(monkeypatch):
    calls = flaky_gh(monkeypatch, ["HTTP 502", "HTTP 502", "HTTP 504: timeout"])
    with pytest.raises(SystemExit, match="HTTP 504"):
        gh_rest.api_list("repos/x/y/issues")
    assert [c for c in calls if not isinstance(c, tuple)] == [2, 4]


@pytest.mark.parametrize(
    "stderr",
    [
        "HTTP 404: Not Found",
        "HTTP 403: blocked",
        "HTTP 422: invalid",
        "HTTP 408: Request Timeout",
    ],
)
def test_a_client_error_is_not_tried_again(monkeypatch, stderr):
    calls = flaky_gh(monkeypatch, [stderr])
    with pytest.raises(SystemExit, match=stderr):
        gh_rest.api("repos/x/y")
    assert len(calls) == 1


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


def pull(number, body):
    return {"number": number, "body": body, "head": {"sha": f"sha{number}"}}


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
        pulls=[pull(40, "Closes #7"), pull(41, "Fixes: #7 and see #5")],
    )
    five, seven = gh_rest.open_issue_nodes(REPO, with_body=True)
    assert five["body"] == "body 5"
    assert five["subIssues"] == {"nodes": [{"number": 7, "state": "OPEN"}]}
    assert five["parent"] is None
    assert seven["parent"] == {"number": 5}
    assert seven["closedByPullRequestsReferences"] == {"totalCount": 2}
    assert seven["closingPullRequests"] == [
        {"number": 40, "headSha": "sha40"},
        {"number": 41, "headSha": "sha41"},
    ]
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
    assert len(gh_rest.closing_prs(12, [pull(1, body)])) == count


def test_a_link_to_another_repo_carries_its_repo(monkeypatch):
    # Its number alone read as this repo's issue with that number (#164).
    here = {
        "number": 3,
        "state": "open",
        "repository_url": f"https://api.github.com/repos/{REPO}",
    }
    there = {
        "number": 3,
        "state": "open",
        "repository_url": "https://api.github.com/repos/dolev2/Other",
    }
    fake_github(
        monkeypatch,
        [rest_issue(5, blocked_by=2)],
        {f"repos/{REPO}/issues/5/dependencies/blocked_by": [here, there]},
    )
    [five] = gh_rest.open_issue_nodes(REPO)
    assert five["blockedBy"]["nodes"] == [
        {"number": 3, "state": "OPEN"},
        {"number": 3, "state": "OPEN", "repository": "dolev2/Other"},
    ]
