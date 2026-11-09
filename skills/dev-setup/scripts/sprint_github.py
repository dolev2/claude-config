"""What sprint_state.py reads from GitHub about branches and PRs, through REST.

Kept apart from sprint_state.py so its logic is tested without a network: `state()`
takes these readers as functions (claude-config #203).
"""

from urllib.parse import quote

from gh_rest import api, api_list

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
    diff = api(f"repos/{repo}/compare/{quote(base)}...{quote(branch)}")
    return {f["filename"] for f in diff.get("files", [])}
