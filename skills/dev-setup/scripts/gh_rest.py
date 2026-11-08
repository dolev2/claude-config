"""Reads open issues from GitHub through REST only, in the shape the scripts expect.

GraphQL is blocked in Claude Code cloud sessions (HTTP 403), and `gh repo view`,
`gh issue` and `gh label list` go through it. REST (`gh api repos/...`) works there and
everywhere else, so the pipeline scripts read through this module always, not only in
the cloud: one code path, tested once (claude-config #133, #138).

`open_issue_nodes` returns each open issue as the GraphQL node the scripts used to
fetch (`labels.nodes`, `milestone`, `blockedBy.nodes`, ...), so their logic and tests
stay as they were. Links are fetched per issue, and only for issues whose REST summary
says they have any.
"""

import json
import re
import subprocess
import sys
import time

REMOTE = re.compile(r"(?:github\.com[:/]|/git/)([^/:]+)/([^/]+?)(?:\.git)?/?$")
CLOSING = r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#{}\b"
NOT_A_REPO = "Not inside a GitHub repo that gh can see; pass --repo owner/name."
CLIENT_ERROR = re.compile(r"HTTP 4\d\d")
TRANSIENT = re.compile(
    r"HTTP 5\d\d|timeout|connection reset|connection refused|\bEOF\b", re.IGNORECASE
)
RETRY_DELAYS = (2, 4)


def run(*args: str) -> tuple[int, str, str]:
    """Run a command; return its exit code, stdout and stderr."""
    p = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def repo_from_url(url: str) -> str | None:
    """owner/name from a GitHub remote URL (https, ssh, or the cloud git proxy)."""
    match = REMOTE.search(url.strip())
    return f"{match[1]}/{match[2]}" if match else None


def current_repo() -> str:
    """owner/name of the `origin` remote of the current directory; exits without one."""
    code, out, _ = run("git", "remote", "get-url", "origin")
    repo = repo_from_url(out) if code == 0 else None
    if not repo:
        sys.exit(NOT_A_REPO)
    return repo


def is_transient(stderr: str) -> bool:
    """True when gh failed for a reason that a second try may not hit.

    An orchestrator runs these scripts dozens of times a sprint (claude-config #174),
    so one dropped connection should not fail a whole check. A 4xx is the request's
    own fault and fails at once, and so does anything not known to be passing: the
    cloud proxy answers 403 for what it blocks, and waiting will not change that.
    """
    if CLIENT_ERROR.search(stderr):
        return False
    return bool(TRANSIENT.search(stderr))


def gh_api(path: str, *flags: str) -> str:
    """stdout of `gh api <flags> <path>`, tried again on a transient failure.

    Exits with gh's error when the last try fails, or at once on any other failure.
    """
    for delay in (*RETRY_DELAYS, None):
        code, out, err = run("gh", "api", *flags, path)
        if code == 0:
            return out
        if delay is None or not is_transient(err):
            sys.exit(f"gh api {path} failed:\n{err}")
        time.sleep(delay)
    raise AssertionError("unreachable")


def api(path: str) -> object:
    """One REST call, as parsed JSON."""
    return json.loads(gh_api(path))


def api_list(path: str) -> list:
    """Every item of a paginated REST list, all pages flattened into one list."""
    pages = json.loads(gh_api(path, "--paginate", "--slurp"))
    return [item for page in pages for item in page]


def ref_repo(item: dict) -> str | None:
    """owner/name of a linked issue, from the end of its `repository_url`."""
    url = item.get("repository_url")
    return "/".join(url.rstrip("/").rsplit("/", 2)[-2:]) if url else None


def refs(repo: str, items: list[dict]) -> dict:
    """GraphQL-style connection of issue references: {"nodes": [{number, state}]}.

    A reference to an issue of another repo also carries its `repository` (owner/name):
    its number alone would read as the issue of `repo` with that number (#164).
    """
    nodes = []
    for item in items:
        node = {"number": item["number"], "state": item["state"].upper()}
        other = ref_repo(item)
        if other and other.lower() != repo.lower():
            node["repository"] = other
        nodes.append(node)
    return {"nodes": nodes}


def links(repo: str, issue: dict, count: int, path: str) -> dict:
    """The linked issues behind `path`, fetched only when the summary counts any."""
    if not count:
        return {"nodes": []}
    return refs(repo, api_list(f"repos/{repo}/issues/{issue['number']}/{path}"))


def to_node(repo: str, issue: dict, with_body: bool) -> dict:
    """A REST issue as the GraphQL node the ranking and audit scripts read."""
    deps = issue.get("issue_dependencies_summary") or {}
    milestone = issue.get("milestone")
    node = {
        "number": issue["number"],
        "title": issue["title"],
        "labels": {"nodes": [{"name": label["name"]} for label in issue["labels"]]},
        "milestone": {
            "title": milestone["title"],
            "number": milestone["number"],
            "state": milestone["state"].upper(),
        }
        if milestone
        else None,
        "blockedBy": links(
            repo, issue, deps.get("total_blocked_by"), "dependencies/blocked_by"
        ),
        "blocking": links(
            repo, issue, deps.get("total_blocking"), "dependencies/blocking"
        ),
    }
    if with_body:
        subs = (issue.get("sub_issues_summary") or {}).get("total")
        node["body"] = issue.get("body") or ""
        node["subIssues"] = links(repo, issue, subs, "sub_issues")
        node["parent"] = parent_ref(repo, issue)
    return node


def closing_prs(number: int, pulls: list[dict]) -> list[dict]:
    """The PRs of `pulls` that close issue `number`: [{number, headSha}].

    Read from a closing keyword in the PR body, so narrower than GraphQL's
    closedByPullRequestsReferences: a full `owner/repo#N` reference, an issue URL, or a
    link made by hand in the Development panel is not counted. The pipeline always
    writes `Closes #N` (git-flow.md).
    """
    pattern = re.compile(CLOSING.format(number), re.IGNORECASE)
    return [
        {"number": pr["number"], "headSha": pr["head"]["sha"]}
        for pr in pulls
        if pattern.search(pr.get("body") or "")
    ]


def parent_ref(repo: str, issue: dict) -> dict | None:
    """{"number": N} of the parent issue, read from the end of `parent_issue_url`.

    A parent of another repo also carries its `repository` (owner/name): its number
    alone would read as the issue of `repo` with that number (claude-config #196).
    """
    url = issue.get("parent_issue_url")
    if not url:
        return None
    repository_url, number = url.rstrip("/").rsplit("/issues/", 1)
    parent = {"number": int(number)}
    other = ref_repo({"repository_url": repository_url})
    if other and other.lower() != repo.lower():
        parent["repository"] = other
    return parent


def open_issue_nodes(repo: str, with_body: bool = False) -> list[dict]:
    """Every open issue of `repo` (pull requests left out), as GraphQL-shaped nodes.

    With `with_body`, each node also carries `body`, `subIssues`, `parent`,
    `closedByPullRequestsReferences` (the fields audit_sprint.py reads) and
    `closingPullRequests` (the open PRs themselves, for sprint_state.py).
    """
    issues = api_list(f"repos/{repo}/issues?state=open&per_page=100")
    nodes = [
        to_node(repo, issue, with_body)
        for issue in issues
        if "pull_request" not in issue
    ]
    if with_body:
        pulls = api_list(f"repos/{repo}/pulls?state=open&per_page=100")
        for node in nodes:
            prs = closing_prs(node["number"], pulls)
            node["closingPullRequests"] = prs
            node["closedByPullRequestsReferences"] = {"totalCount": len(prs)}
    return nodes
