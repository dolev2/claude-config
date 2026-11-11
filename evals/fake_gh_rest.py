"""The `gh api` side of fake_gh.py: the REST routes of reference/cloud.md's table."""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import fake_gh_graphql
from fake_gh_state import GhError, State, not_found

VALUE_FLAGS = {"-X", "--method", "-f", "--raw-field", "-F", "--field", "--input", "-H"}
VALUE_FLAGS |= {"--header", "--cache", "-p", "--preview", "--template", "-t"}


def parse(args: list[str]) -> tuple[str, str, dict, bool]:
    """path, method, request body and --slurp from a `gh api` argument list."""
    path, method, fields, slurp, i = "", "", {}, False, 0
    while i < len(args):
        arg = args[i]
        value = args[i + 1] if i + 1 < len(args) else ""
        if arg in ("-X", "--method"):
            method = value.upper()
        elif arg in ("-f", "--raw-field", "-F", "--field"):
            key, _, raw = value.partition("=")
            typed = arg in ("-F", "--field")
            add_field(fields, key, typed_value(raw) if typed else raw)
        elif arg == "--input":
            text = sys.stdin.read() if value == "-" else Path(value).read_text("utf-8")
            fields.update(json.loads(text or "{}"))
        elif arg == "--slurp":
            slurp = True
        if arg in VALUE_FLAGS:
            i += 2
            continue
        if not arg.startswith("-") and not path:
            path = arg
        i += 1
    return path, method or ("POST" if fields else "GET"), fields, slurp


def add_field(fields: dict, key: str, value: object) -> None:
    """-f k=v, and -f k[]=v for a list."""
    if key.endswith("[]"):
        fields.setdefault(key[:-2], []).append(value)
    else:
        fields[key] = value


def typed_value(raw: str) -> object:
    """-F's typing: true, false, null and integers."""
    literals = {"true": True, "false": False, "null": None}
    if raw in literals:
        return literals[raw]
    return int(raw) if raw.isdigit() else raw


def issue_rest(state: State, number: int) -> dict:
    """An issue as the REST API returns it."""
    issue = state.issue(number)
    title = issue.get("milestone")
    numbered = {m["title"]: m for m in milestones(state)}
    milestone = numbered.get(title) or (
        {"title": title, "number": 1, "state": "open"} if title else None
    )
    return {
        "id": 1000 + number,
        "number": number,
        "title": issue.get("title", ""),
        "body": issue.get("body", ""),
        "state": issue.get("state", "open"),
        "labels": [{"name": label} for label in issue.get("labels", [])],
        "milestone": milestone,
        "html_url": state.issue_url(number),
        "repository_url": f"https://api.github.com/repos/{state.repo}",
        "user": {"login": "dolev2"},
        "issue_dependencies_summary": {
            "total_blocked_by": len(issue.get("blocked_by", [])),
            "total_blocking": len(state.blocking(number)),
        },
        "sub_issues_summary": {"total": len(issue.get("sub_issues", []))},
    }


def pull_rest(state: State, number: int) -> dict:
    """A PR as the REST API returns it."""
    pull = state.pull(number)
    mergeable = pull.get("mergeable", True)
    return {
        "number": number,
        "title": pull.get("title", ""),
        "body": pull.get("body", ""),
        "state": "closed" if pull.get("merged") else pull.get("state", "open"),
        "merged": bool(pull.get("merged")),
        "head": {"ref": pull["head"], "sha": state.head_sha(pull)},
        "base": {"ref": pull.get("base", state.default_branch)},
        "mergeable": mergeable,
        "mergeable_state": "clean" if mergeable else "dirty",
        "html_url": state.pull_url(number),
    }


def timeline(state: State, number: int) -> list[dict]:
    """cross-referenced events for the PRs that close the issue."""
    state.issue(number)
    events = []
    for pr in state.closing_pulls(number):
        source = pull_rest(state, pr) | {"pull_request": {"url": state.pull_url(pr)}}
        events.append({"event": "cross-referenced", "source": {"issue": source}})
    return events


def issues_list(state: State, query: dict) -> list[dict]:
    """GET issues?state=&labels=, without PRs (they live under pulls here)."""
    wanted = query.get("state", ["open"])[0]
    labels = [x for x in query.get("labels", [""])[0].split(",") if x]
    milestone_filter = query.get("milestone", [None])[0]
    rows = []
    for n in state.issue_numbers():
        if not state.issue_matches(n, labels, None, wanted):
            continue
        row = issue_rest(state, n)
        if milestone_filter and str((row["milestone"] or {}).get("number")) != str(
            milestone_filter
        ):
            continue
        rows.append(row)
    return rows


def pulls_list(state: State, query: dict) -> list[dict]:
    """GET pulls?state=&head=owner:branch."""
    wanted = query.get("state", ["open"])[0]
    head = query.get("head", [""])[0].split(":")[-1] or None
    return [
        pull_rest(state, n)
        for n in state.pull_numbers()
        if state.pull_matches(n, head, "closed" if wanted == "closed" else wanted, None)
    ]


def read_only(method: str, answer: Callable[[], object]) -> object:
    """A GET-only route: any other method is not modelled, so it fails loudly."""
    if method != "GET":
        raise GhError(f"fake gh: unsupported: {method} here", unsupported=True)
    return answer()


def issue_update(state: State, number: int, method: str, body: dict) -> dict:
    """GET or PATCH issues/N: body, title, state, labels."""
    if method != "PATCH":
        return read_only(method, lambda: issue_rest(state, number))
    issue = state.issue(number)
    for key in ("title", "body", "state"):
        if key in body:
            issue[key] = body[key]
    if "labels" in body:
        issue["labels"] = []
        state.add_labels(number, list(body["labels"]))
    return issue_rest(state, number)


def labels_route(state: State, number: int, method: str, body: dict) -> list[dict]:
    """POST issues/N/labels adds; GET lists."""
    if method == "POST":
        state.add_labels(number, list(body.get("labels", [])))
    elif method == "PUT":
        state.issue(number)["labels"] = []
        state.add_labels(number, list(body.get("labels", [])))
    return [{"name": x} for x in state.issue(number).get("labels", [])]


def comments_route(state: State, number: int, method: str, body: dict) -> object:
    """POST issues/N/comments adds; GET lists."""
    if method == "POST":
        state.add_comment(number, body.get("body", ""))
        return {"body": body.get("body", ""), "html_url": state.issue_url(number)}
    return [
        {"body": c, "user": {"login": "dolev2"}}
        for c in state.thread(number).get("comments", [])
    ]


def related(state: State, number: int, key: str) -> list[dict]:
    """sub_issues or dependencies/blocked_by: the listed issues, open or closed."""
    numbers = state.issue(number).get(key, [])
    return [issue_rest(state, n) for n in numbers if str(n) in state.data["issues"]]


def merge_route(state: State, number: int, method: str) -> dict:
    """PUT pulls/N/merge."""
    if method != "PUT":
        raise GhError("fake gh: unsupported: merge without PUT", unsupported=True)
    state.merge(number)
    return {"merged": True, "message": "Pull Request successfully merged"}


def check_runs(state: State, sha: str) -> dict:
    """GET commits/SHA/check-runs: the checks of the PR whose head is SHA."""
    for n in state.pull_numbers():
        if state.head_sha(state.pull(n)) == sha:
            run = {"name": "tests", "status": "completed"}
            return {
                "total_count": 1,
                "check_runs": [run | {"conclusion": state.checks(n)}],
            }
    return {"total_count": 0, "check_runs": []}


def routes(state: State, method: str, body: dict) -> list[tuple[str, Callable]]:
    """The routes under repos/{owner}/{repo}, as (regex, handler of the match)."""
    i = int
    return [
        (r"", lambda m, q: repo_info(state, method, body)),
        (
            r"/labels",
            lambda m, q: read_only(
                method, lambda: [{"name": x} for x in state.data["labels"]]
            ),
        ),
        (r"/milestones", lambda m, q: read_only(method, lambda: milestones(state))),
        (r"/issues", lambda m, q: read_only(method, lambda: issues_list(state, q))),
        (r"/issues/(\d+)", lambda m, q: issue_update(state, i(m[1]), method, body)),
        (
            r"/issues/(\d+)/labels",
            lambda m, q: labels_route(state, i(m[1]), method, body),
        ),
        (
            r"/issues/(\d+)/labels/(.+)",
            lambda m, q: remove_label(state, i(m[1]), unquote(m[2])),
        ),
        (
            r"/issues/(\d+)/comments",
            lambda m, q: comments_route(state, i(m[1]), method, body),
        ),
        (
            r"/issues/(\d+)/sub_issues",
            lambda m, q: related(state, i(m[1]), "sub_issues"),
        ),
        (
            r"/issues/(\d+)/dependencies/blocked_by",
            lambda m, q: related(state, i(m[1]), "blocked_by"),
        ),
        (
            r"/issues/(\d+)/dependencies/blocking",
            lambda m, q: [issue_rest(state, n) for n in state.blocking(i(m[1]))],
        ),
        (r"/issues/(\d+)/timeline", lambda m, q: timeline(state, i(m[1]))),
        (r"/pulls", lambda m, q: read_only(method, lambda: pulls_list(state, q))),
        (
            r"/pulls/(\d+)",
            lambda m, q: read_only(method, lambda: pull_rest(state, i(m[1]))),
        ),
        (r"/pulls/(\d+)/merge", lambda m, q: merge_route(state, i(m[1]), method)),
        (r"/commits/([0-9a-f]+)/check-runs", lambda m, q: check_runs(state, m[1])),
        (
            r"/git/matching-refs/heads/(.+)",
            lambda m, q: matching_refs(state, unquote(m[1])),
        ),
    ]


def repo_info(state: State, method: str, body: dict) -> dict:
    """GET (or PATCH) repos/{owner}/{repo}."""
    if method == "PATCH":
        state.data.setdefault("settings", {}).update(body)
    settings = state.data.get("settings", {})
    return {
        "full_name": state.repo,
        "default_branch": state.default_branch,
        "visibility": "private",
        "delete_branch_on_merge": settings.get("delete_branch_on_merge", True),
    }


def milestones(state: State) -> list[dict]:
    return [
        {"number": n, "state": "open"} | m
        for n, m in enumerate(state.data["milestones"], start=1)
    ]


def remove_label(state: State, number: int, label: str) -> list[dict]:
    """DELETE issues/N/labels/L: 404 when the issue does not carry it."""
    if label not in state.issue(number).get("labels", []):
        raise GhError("gh: Label does not exist (HTTP 404)")
    state.remove_labels(number, [label])
    return [{"name": x} for x in state.issue(number)["labels"]]


def matching_refs(state: State, branch: str) -> list[dict]:
    """GET git/matching-refs/heads/B, from the bare remote."""
    remote = state.data.get("git_remote")
    if not remote:
        return []
    refs = state.git(f"--git-dir={remote}", "for-each-ref", "--format=%(refname)")
    prefix = f"refs/heads/{branch}"
    return [{"ref": r} for r in refs.splitlines() if r.startswith(prefix)]


def handle(args: list[str], state: State) -> object:
    """Answer one `gh api` call; GhError for a 404 or an unknown route."""
    path, method, body, slurp = parse(args)
    if path == "graphql":
        query = str(body.pop("query", ""))
        return fake_gh_graphql.handle(query, body, state)
    url = urlsplit(path.lstrip("/"))
    query = parse_qs(url.query)
    owner_repo = re.escape(state.repo)
    route = re.sub(r"^repos/\{owner\}/\{repo\}", f"repos/{state.repo}", url.path)
    if route.startswith("repos/") and not re.match(rf"repos/{owner_repo}(/|$)", route):
        raise not_found()
    rest = route[len(f"repos/{state.repo}") :]
    for pattern, handler in routes(state, method, body):
        match = re.fullmatch(pattern, rest)
        if match:
            result = handler(match, query)
            return [result] if slurp else result
    raise GhError(f"fake gh: unsupported: api {method} {path}", unsupported=True)
