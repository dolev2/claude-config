"""What sprint_state.py reads from GitHub about branches and PRs, through REST.

Kept apart from sprint_state.py so its logic is tested without a network: `state()`
takes these readers as functions (claude-config #203).
"""

import json
import re
from datetime import UTC, datetime
from urllib.parse import quote

from gh_rest import api, api_list, closing_prs, gh_api, other_repo
from gh_rest import run as run_command

SPEC_BRANCH = "claude/spec-"
FAILED = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}


def ci_summary(check_runs: list[dict]) -> str:
    """One word for a commit's checks: none, pending, failure or success."""
    if not check_runs:
        return "none"
    if any(run["status"] != "completed" for run in check_runs):
        return "pending"
    if any(run["conclusion"] in FAILED for run in check_runs):
        return "failure"
    return "success"


def pr_status(repo: str, pr: dict) -> dict:
    """mergeable_state and CI of one open PR, from GitHub."""
    pull = api(f"repos/{repo}/pulls/{pr['number']}")
    checks = api(f"repos/{repo}/commits/{pr['headSha']}/check-runs?per_page=100")
    return {
        "mergeable_state": pull["mergeable_state"],
        "ci": ci_summary(checks["check_runs"]),
    }


def pr_files(repo: str, number: int) -> set[str]:
    """The files an open PR changes."""
    return {f["filename"] for f in api_list(f"repos/{repo}/pulls/{number}/files")}


def branch_exists(repo: str, branch: str) -> bool:
    """True when `branch` is on GitHub; matching-refs answers [] rather than a 404."""
    refs = api(f"repos/{repo}/git/matching-refs/heads/{quote(branch)}")
    return any(ref["ref"] == f"refs/heads/{branch}" for ref in refs)


def branch_files(repo: str, base: str, branch: str) -> set[str]:
    """The files `branch` already changed against `base`; none when it is not pushed.

    A planning child creates its branch on GitHub with nothing on it yet, and a branch
    may not exist at all, so an empty set is the ordinary answer.
    """
    if not branch_exists(repo, branch):
        return set()
    path = f"repos/{repo}/compare/{quote(base)}...{quote(branch)}"
    code, out, err = run_command("gh", "api", path)
    if code != 0 and "HTTP 404" in err:
        # Deleted since the check above, or no history shared with base.
        return set()
    diff = json.loads(out) if code == 0 else json.loads(gh_api(path))
    return {f["filename"] for f in diff.get("files", [])}


def referencing_prs(repo: str, number: int) -> list[int]:
    """The PRs of `repo` that mention issue `number`, from its timeline (REST).

    `Refs #N` in a PR body leaves a `cross-referenced` event on the issue; a PR of
    another repo is left out, since its number is not this repo's.
    """
    events = api_list(f"repos/{repo}/issues/{number}/timeline?per_page=100")
    found = set()
    for event in events:
        source = (event.get("source") or {}).get("issue") or {}
        if event.get("event") != "cross-referenced" or "pull_request" not in source:
            continue
        if other_repo(repo, source.get("repository_url")) is None:
            found.add(source["number"])
    return sorted(found)


def links_issue(body: str, number: int) -> bool:
    """True when a PR body links issue `number`: `Refs #N` or `Closes #N` (specs.md).

    A spec PR that only mentions the issue (in its table of parts, say) is not its
    spec PR, though GitHub leaves the same cross-reference (claude-config #334).
    """
    link = rf"\b(?:refs|closes)\s+#{number}\b"
    return re.search(link, body, re.IGNORECASE) is not None


def spec_prs(repo: str, number: int) -> list[dict]:
    """The spec PRs (`claude/spec-*`) whose body links issue `number`.

    Each is {number, state, branch, body, headSha}; state is "open", "merged" or
    "closed" (closed without a merge). sprint_proposals.py reads the stage from them.
    """
    found = []
    for pr_number in referencing_prs(repo, number):
        pull = api(f"repos/{repo}/pulls/{pr_number}")
        branch = pull["head"]["ref"]
        body = pull.get("body") or ""
        if not branch.startswith(SPEC_BRANCH) or not links_issue(body, number):
            continue
        merged = pull.get("merged_at") is not None
        found.append(
            {
                "number": pr_number,
                "state": "merged" if merged else pull["state"],
                "branch": branch,
                "body": body,
                "headSha": pull["head"]["sha"],
            }
        )
    return found


def moment(text: str) -> datetime:
    """An ISO time as an aware datetime; one without a zone is taken as UTC."""
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def done_since(repo: str, sprint: str, since: str) -> list[dict]:
    """The sprint's issues that closed in status:done at or after `since` (ISO).

    REST's `since` filters by update time, so a later edit of an issue closed before
    `since` would pass it: `closed_at` decides (handover_prompt.py, S-2.12).
    """
    issues = api_list(
        f"repos/{repo}/issues?state=closed&labels=status:done"
        f"&since={quote(since)}&per_page=100"
    )
    return [
        {"number": i["number"], "title": i["title"]}
        for i in sorted(issues, key=lambda i: i.get("closed_at") or "")
        if "pull_request" not in i
        and (i.get("milestone") or {}).get("title") == sprint
        and i.get("closed_at")
        and moment(i["closed_at"]) >= moment(since)
    ]


def issue_summary(repo: str, number: int) -> dict:
    """{number, title, status} of one issue; status is its `status:` label, or None."""
    issue = api(f"repos/{repo}/issues/{number}")
    labels = [label["name"] for label in issue.get("labels", [])]
    status = next((n for n in labels if n.startswith("status:")), None)
    return {"number": number, "title": issue["title"], "status": status}


def open_prs_of(repo: str, numbers: list[int]) -> dict[int, int]:
    """Each issue of `numbers` that an open PR closes (`Closes #N`) → that PR.

    A repair child's issue is not in the merge queue, but its PR is still open and
    followed, so the hand-off reads it here (handover_prompt.py).
    """
    if not numbers:
        return {}
    pulls = api_list(f"repos/{repo}/pulls?state=open&per_page=100")
    found = {n: closing_prs(n, pulls) for n in numbers}
    return {n: prs[0]["number"] for n, prs in found.items() if prs}
