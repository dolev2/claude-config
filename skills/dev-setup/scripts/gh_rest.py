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

REMOTE = re.compile(r"(?:github\.com[:/]|/git/)([^/:]+)/([^/]+?)(?:\.git)?/?$")
CLOSING = r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#{}\b"
NOT_A_REPO = "Not inside a GitHub repo that gh can see; pass --repo owner/name."


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


def api(path: str) -> object:
    """One REST call; exits with gh's error when it fails."""
    code, out, err = run("gh", "api", path)
    if code != 0:
        sys.exit(f"gh api {path} failed:\n{err}")
    return json.loads(out)


def api_list(path: str) -> list:
    """Every item of a paginated REST list, all pages flattened into one list."""
    code, out, err = run("gh", "api", "--paginate", "--slurp", path)
    if code != 0:
        sys.exit(f"gh api {path} failed:\n{err}")
    return [item for page in json.loads(out) for item in page]


def refs(items: list[dict]) -> dict:
    """GraphQL-style connection of issue references: {"nodes": [{number, state}]}."""
    return {
        "nodes": [{"number": i["number"], "state": i["state"].upper()} for i in items]
    }


def links(repo: str, issue: dict, count: int, path: str) -> dict:
    """The linked issues behind `path`, fetched only when the summary counts any."""
    if not count:
        return {"nodes": []}
    return refs(api_list(f"repos/{repo}/issues/{issue['number']}/{path}"))


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
        node["parent"] = parent_ref(issue)
    return node


def closing_pr_count(number: int, pulls: list[dict]) -> int:
    """How many of `pulls` close issue `number` with a keyword in their body.

    Narrower than GraphQL's closedByPullRequestsReferences: a full `owner/repo#N`
    reference, an issue URL, or a link made by hand in the Development panel is not
    counted. The pipeline always writes `Closes #N` (git-flow.md), and the count only
    feeds the audit's merge-candidate hint.
    """
    pattern = re.compile(CLOSING.format(number), re.IGNORECASE)
    return sum(1 for pr in pulls if pattern.search(pr.get("body") or ""))


def parent_ref(issue: dict) -> dict | None:
    """{"number": N} of the parent issue, read from the end of `parent_issue_url`."""
    url = issue.get("parent_issue_url")
    return {"number": int(url.rstrip("/").rsplit("/", 1)[1])} if url else None


def open_issue_nodes(repo: str, with_body: bool = False) -> list[dict]:
    """Every open issue of `repo` (pull requests left out), as GraphQL-shaped nodes.

    With `with_body`, each node also carries `body`, `subIssues`, `parent` and
    `closedByPullRequestsReferences`, the fields audit_sprint.py reads.
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
            node["closedByPullRequestsReferences"] = {
                "totalCount": closing_pr_count(node["number"], pulls)
            }
    return nodes
