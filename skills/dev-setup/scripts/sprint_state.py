"""The state of the current sprint as one JSON object, for the sprint orchestrator.

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a logged-in
`gh`:

    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/sprint_state.py"                    # nothing claimed yet
    python "$S/sprint_state.py" --claimed 164,172  # issues that already have a session

The orchestrator (claude-config #150) keeps no memory between checks: every check runs
this and rebuilds its picture from GitHub. Which issue already has a child session is
not on GitHub, so the orchestrator reads it from the sessions' `issue:<N>` tags and
passes it in --claimed (claude-config #174). A claimed issue outside the sprint holds
nothing back: its planned files are not read.

The keys:

    dispatch         ready for a child session: Claude's turn, no open blocker, not an
                     umbrella, not costs-money, not claimed, no file shared with work in
                     flight. Repairs first, then bugs, then approved plans, then plans
                     to write.
    held_by_overlap  would be in dispatch, but shares a planned file with work in flight
                     (claimed, in review, or earlier in dispatch), so it runs after it
    blocked          Claude's turn, waiting on an open blocker
    umbrellas        would be in dispatch, but a sub-issue is still open: the issue
                     and its open sub-issues (#N, or owner/name#N in another repo)
    waiting_dolev    plan questions, plans to approve, PRs to review
    merge_queue      in review with an open PR: its head, mergeable_state and CI.
                     mergeable_state "unknown" means GitHub is still computing it:
                     not yet, ask again next check (cloud.md)
    on_hold          costs-money, until Dolev approves the expense
    findings         audit_sprint.py's findings, as data
    pipeline_sha     the last commit on the pipeline's main that touched what is read
                     from disk on every use (RELOAD_PATHS): when it moves, the
                     orchestrator refreshes ~/.claude and reads the skills again
    session_sha      the last commit on the pipeline's main that touched what a session
                     loads once, at its start (SESSION_PATHS): when it moves, the
                     orchestrator asks for a new orchestrator session and stops
                     (orchestrate.md, "שינוי בצינור באמצע ספרינט")

Both shas are read with git, from a blob-less bare clone kept in CACHE, never from the
REST API: a cloud session reaches the API only of the repos attached to it, and an
orchestrator of a project repo has only its project (claude-config #211). Not from
~/.claude either: that is a one-commit clone, where `git log -- <path>` always names its
single commit. When git fails, both are null with a warning on stderr, and the rest of
the state is printed as usual. A cache git cannot use is deleted and cloned again once;
two runs racing on it only make one of them print nulls.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from audit_sprint import SprintIssue, audit, is_local, is_shared_doc, sprint_issue
from gh_rest import api, current_repo, open_issue_nodes
from rank_issues import Issue, current_sprint, parse_issue, rank

PIPELINE_URL = "https://github.com/dolev2/claude-config"
CACHE = Path.home() / ".cache" / "claude-config-pipeline.git"
GIT_TIMEOUT_SECONDS = 60
DISPATCH_ORDER = ["needs-repair", "ready-to-execute", "explore"]
DOLEV_TURN = ["plan-questions", "waiting-approval", "in-review"]
PROMPTS = {
    "explore": "תחקור את #{}",
    "ready-to-execute": "תקודד את #{}",
    "needs-repair": "תקודד את #{}",
}
# The two groups of the pipeline repo's paths (claude-config #192). A hook's script is
# read from disk on every run, so it reloads; registering a hook is a settings.json
# change, so it does not.
RELOAD_PATHS = ["skills", "hooks"]
SESSION_PATHS = ["CLAUDE.md", "rules", "settings.json"]
FAILED = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}


def claimed_list(text: str) -> list[int]:
    """--claimed: comma-separated issue numbers; an empty string is none."""
    try:
        return [int(part) for part in text.split(",") if part.strip()]
    except ValueError as err:
        message = f"not a list of issue numbers: {text}"
        raise argparse.ArgumentTypeError(message) from err


def open_subs(node: dict) -> list[str]:
    """The issue's open sub-issues: #N, or owner/name#N for another repo."""
    subs = (node.get("subIssues") or {}).get("nodes") or []
    return [
        f"#{s['number']}" if is_local(s) else f"{s['repository']}#{s['number']}"
        for s in subs
        if s.get("state") == "OPEN"
    ]


def is_umbrella(node: dict) -> bool:
    """An issue with an open sub-issue is not worked on itself (dependencies.md).

    Once every sub-issue is closed, the issue is ordinary work again (#211).
    """
    return bool(open_subs(node))


def shared_files(a: SprintIssue, b: SprintIssue) -> list[str]:
    """Planned files both issues change, without README.md and CLAUDE.md."""
    return sorted(f for f in a.files & b.files if not is_shared_doc(f))


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


def git(*args: str) -> str:
    """Runs git without prompting for credentials; its stdout. Raises on failure."""
    env = os.environ | {"GIT_TERMINAL_PROMPT": "0"}
    done = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    return done.stdout


def refresh_cache(cache: Path) -> None:
    """Clones the pipeline repo into `cache` once, then brings its main up to date.

    Full history without blobs: `git log -- <path>` compares trees, never file contents.
    """
    if not (cache / "HEAD").exists():
        git("clone", "-q", "--bare", "--filter=blob:none", PIPELINE_URL, str(cache))
    git("-C", str(cache), "fetch", "-q", "origin", "+refs/heads/main:refs/heads/main")


def last_commit(cache: Path, paths: list[str]) -> str | None:
    """The newest commit on the cached main that touched any of `paths`, or None."""
    out = git("-C", str(cache), "log", "-1", "--format=%H", "main", "--", *paths)
    return out.strip() or None


def read_shas(cache: Path) -> dict:
    """Refreshes the cache and reads both shas from it. Raises when git fails."""
    refresh_cache(cache)
    return {
        "pipeline_sha": last_commit(cache, RELOAD_PATHS),
        "session_sha": last_commit(cache, SESSION_PATHS),
    }


def pipeline_shas(cache: Path) -> dict:
    """pipeline_sha and session_sha; both None, with a warning, when git fails.

    A cache git cannot use (half cloned, corrupt) would fail every later check, so on a
    failure it is deleted and cloned again, once.
    """
    try:
        try:
            return read_shas(cache)
        except subprocess.CalledProcessError:
            shutil.rmtree(cache, ignore_errors=True)
            return read_shas(cache)
    except (subprocess.SubprocessError, OSError) as err:
        detail = getattr(err, "stderr", None) or str(err)
        print(
            f"warning: pipeline shas not read, the pipeline-change check did not run: "
            f"{detail.strip()}",
            file=sys.stderr,
        )
        return {"pipeline_sha": None, "session_sha": None}


def dispatch_split(
    candidates: list[Issue], audited: dict[int, SprintIssue], in_flight: list[int]
) -> tuple[list[dict], list[dict]]:
    """(dispatch, held_by_overlap), in ranking order.

    Each issue put in dispatch counts as in flight for the ones after it, so two
    ready issues that share a file never go out together.
    """
    flying = list(in_flight)
    dispatch, held = [], []
    for issue in candidates:
        clashes = {
            other: shared_files(audited[issue.number], audited[other])
            for other in flying
        }
        clashes = {other: files for other, files in clashes.items() if files}
        if clashes:
            files = sorted({f for shared in clashes.values() for f in shared})
            held.append(
                {"number": issue.number, "with": sorted(clashes), "files": files}
            )
            continue
        flying.append(issue.number)
        dispatch.append(
            {
                "number": issue.number,
                "title": issue.title,
                "status": issue.status,
                "kind": issue.kind,
                "waiting": issue.waiting,
                "prompt": PROMPTS[issue.status].format(issue.number),
            }
        )
    return dispatch, held


def state(
    nodes: list[dict],
    sprint: str,
    claimed: list[int],
    status_of: Callable[[dict], dict],
) -> dict:
    """The sprint's state; `status_of(pr)` gives mergeable_state and CI of a PR."""
    in_sprint = [
        n for n in nodes if n["milestone"] and n["milestone"]["title"] == sprint
    ]
    by_number = {n["number"]: n for n in in_sprint}
    issues = rank([parse_issue(n) for n in in_sprint], DISPATCH_ORDER + DOLEV_TURN)
    audited = {n["number"]: sprint_issue(n) for n in in_sprint}

    claude_turn = [i for i in issues if i.status in DISPATCH_ORDER]
    eligible = [
        i
        for i in claude_turn
        if not i.blocked and not i.costs_money and i.number not in claimed
    ]
    umbrellas = [i for i in eligible if is_umbrella(by_number[i.number])]
    candidates = [i for i in eligible if i not in umbrellas]
    # Bug-first is a rule for what Claude picks (#202); Dolev's lists keep the tier
    # first, so his questions come in the same order as before.
    dolev_turn = sorted(
        (i for i in issues if i.status in DOLEV_TURN),
        key=lambda i: DOLEV_TURN.index(i.status),
    )
    in_review = [i.number for i in dolev_turn if i.status == "in-review"]
    in_flight = [n for n in claimed if n in audited] + in_review
    dispatch, held = dispatch_split(candidates, audited, in_flight)

    merge_queue = [
        {"number": i.number, "pr": pr["number"], "head_sha": pr["headSha"]}
        | status_of(pr)
        for i in dolev_turn
        if i.status == "in-review"
        for pr in by_number[i.number]["closingPullRequests"]
    ]
    return {
        "sprint": sprint,
        "dispatch": dispatch,
        "held_by_overlap": held,
        "blocked": [
            {
                "number": i.number,
                "blocked_by": i.open_blockers,
                "outside_blockers": i.outside_blockers,
            }
            for i in claude_turn
            if i.blocked
        ],
        "waiting_dolev": [
            {"number": i.number, "title": i.title, "status": i.status}
            for i in dolev_turn
        ],
        "merge_queue": merge_queue,
        "umbrellas": [
            {"number": i.number, "open_subs": open_subs(by_number[i.number])}
            for i in umbrellas
        ],
        "on_hold": [i.number for i in claude_turn if i.costs_money],
        "findings": [f.as_dict() for f in audit(list(audited.values()))],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--milestone", help="defaults to the current sprint")
    parser.add_argument(
        "--repo", help="owner/name; defaults to the repo of the current directory"
    )
    parser.add_argument(
        "--claimed",
        type=claimed_list,
        default=[],
        help="comma-separated issues that already have a child session",
    )
    args = parser.parse_args(argv)

    repo = args.repo or current_repo()
    nodes = open_issue_nodes(repo, with_body=True)
    sprint = args.milestone or current_sprint(nodes)
    if sprint is None:
        sys.exit("No open milestone has open issues.")
    result = state(nodes, sprint, args.claimed, lambda pr: pr_status(repo, pr))
    result |= pipeline_shas(CACHE)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
