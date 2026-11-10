"""The state of the current sprint as one JSON object, for the sprint orchestrator.

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a logged-in
`gh`:

    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/sprint_state.py"                    # nothing claimed yet
    python "$S/sprint_state.py" --claimed 164,172  # issues that already have a session
    python "$S/sprint_state.py" --spec             # plus spec_gaps (claude-config #227)

The orchestrator (claude-config #150) keeps no memory between checks: every check runs
this and rebuilds its picture from GitHub. Which issue already has a child session is
not on GitHub, so the orchestrator reads it from the `issue:<N>` tags of this repo's
sessions (the `repo:<owner>/<name>` tag) and passes it in --claimed (claude-config
#174). A claimed issue outside the sprint holds nothing back: its planned files are
not read.

The keys:

    dispatch         ready for a child session: Claude's turn, no open blocker, not an
                     umbrella, not costs-money, not claimed, no file shared with work in
                     flight. Repairs first, then bugs, then approved plans, then plans
                     to write.
    held_by_overlap  would be in dispatch, but shares a planned file with work in flight
                     (claimed, in review, or earlier in dispatch), so it runs after it.
                     Work in flight counts its planned files and the files its Plan's
                     branch already changed (claude-config #203)
    blocked          Claude's turn, waiting on an open blocker
    umbrellas        would be in dispatch, but a sub-issue is still open: the issue
                     and its open sub-issues (#N, or owner/name#N in another repo)
    waiting_dolev    plan questions, plans to approve, PRs to review
    merge_queue      in review with an open PR: its head, mergeable_state and CI.
                     mergeable_state "unknown" means GitHub is still computing it:
                     not yet, ask again next check (cloud.md). overlaps: the other
                     work in flight that shares a file the PR changes, [{number, files}]
    on_hold          costs-money, until Dolev approves the expense
    findings         audit_sprint.py's findings, as data
    pipeline_sha     the last commit on the pipeline's main that touched what is read
                     from disk on every use (pipeline_shas.py): when it moves, the
                     orchestrator refreshes ~/.claude and reads the skills again
    session_sha      the last commit on the pipeline's main that touched what a session
                     loads once, at its start (pipeline_shas.py): when it moves, the
                     orchestrator asks for a new orchestrator session and stops
                     (orchestrate.md, "שינוי בצינור באמצע ספרינט")
    spec_gaps        only with --spec: spec_check.py's gaps between ALL open issues and
                     the specs on origin/<default>, as [{path, line, message}]. An
                     error in a spec file is not here: that is CI's job (spec_check.py).
                     Specs that could not be read are one gap that says so
"""

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from audit_sprint import SprintIssue, audit, is_local, is_shared_doc, sprint_issue
from gh_rest import api, current_repo, open_issue_nodes
from issue_body import plan_branch, sections
from pipeline_shas import CACHE, pipeline_shas
from rank_issues import Issue, current_sprint, parse_issue, rank
from spec_check import gaps, git, parse_spec, spec_files_at
from sprint_github import branch_files, pr_files, pr_status

DISPATCH_ORDER = ["needs-repair", "ready-to-execute", "explore"]
DOLEV_TURN = ["plan-questions", "waiting-approval", "in-review"]
PROMPTS = {
    "explore": "תחקור את #{}",
    "ready-to-execute": "תקודד את #{}",
    "needs-repair": "תקודד את #{}",
}


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


def shared_files(a: set[str], b: set[str]) -> list[str]:
    """Files in both sets, without README.md and CLAUDE.md."""
    return sorted(f for f in a & b if not is_shared_doc(f))


def no_files(_: object) -> set[str]:
    """The default reader of changed files: nothing read from GitHub."""
    return set()


def work_files(
    in_sprint: list[dict],
    audited: dict[int, SprintIssue],
    in_flight: list[int],
    files_of_branch: Callable[[str], set[str]],
) -> dict[int, set[str]]:
    """Each issue's planned files; for work in flight, plus what its branch changed.

    A child may change a file its Plan never named (#196 after #164), so the planned
    list alone misses the overlap (claude-config #203).
    """
    files = {number: issue.files for number, issue in audited.items()}
    for node in in_sprint:
        if node["number"] in in_flight:
            branch = plan_branch(sections(node.get("body") or "").get("plan", ""))
            if branch:
                files[node["number"]] = files[node["number"]] | files_of_branch(branch)
    return files


def overlaps(
    issue: int, changed: set[str], files: dict[int, set[str]], in_flight: list[int]
) -> list[dict]:
    """The other work in flight that shares a file with `changed`: [{number, files}]."""
    found = (
        {"number": other, "files": shared_files(changed, files[other])}
        for other in sorted(set(in_flight) - {issue})
    )
    return [row for row in found if row["files"]]


def dispatch_split(
    candidates: list[Issue], files: dict[int, set[str]], in_flight: list[int]
) -> tuple[list[dict], list[dict]]:
    """(dispatch, held_by_overlap), in ranking order.

    Each issue put in dispatch counts as in flight for the ones after it, so two
    ready issues that share a file never go out together.
    """
    flying = list(in_flight)
    dispatch, held = [], []
    for issue in candidates:
        clashes = {
            other: shared_files(files[issue.number], files[other]) for other in flying
        }
        clashes = {other: shared for other, shared in clashes.items() if shared}
        if clashes:
            held_on = sorted({f for shared in clashes.values() for f in shared})
            held.append(
                {"number": issue.number, "with": sorted(clashes), "files": held_on}
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
    files_of_branch: Callable[[str], set[str]] = no_files,
    files_of_pr: Callable[[int], set[str]] = no_files,
) -> dict:
    """The sprint's state, with what it reads from GitHub passed in as functions.

    `status_of(pr)` gives mergeable_state and CI of a PR, `files_of_branch(branch)` the
    files a branch changed, and `files_of_pr(number)` the files a PR changes.
    """
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
    files = work_files(in_sprint, audited, in_flight, files_of_branch)
    dispatch, held = dispatch_split(candidates, files, in_flight)

    merge_queue = [
        {"number": i.number, "pr": pr["number"], "head_sha": pr["headSha"]}
        | status_of(pr)
        | {"overlaps": overlaps(i.number, files_of_pr(pr["number"]), files, in_flight)}
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


def spec_gaps(nodes: list[dict], files: dict[str, str]) -> list[dict]:
    """spec_check's gaps between the open issues `nodes` and the spec `files`.

    Every open issue counts, not only the sprint's: a spec part is covered by any open
    issue that points at it. The parse errors of a file are dropped (CI reports them).
    """
    specs = {path: parse_spec(text)[0] for path, text in files.items()}
    issues = [
        {
            "number": n["number"],
            "labels": {label["name"] for label in n["labels"]["nodes"]},
            "body": n.get("body") or "",
        }
        for n in nodes
    ]
    return [finding._asdict() for finding in gaps(specs, issues)]


def repo_specs(base: str) -> dict[str, str]:
    """The spec files on origin/<base>: the local clone may be behind GitHub.

    They are read from the clone of the current directory, which is the repo the
    orchestrator runs in; --repo naming another repo does not move them.
    """
    root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
    # Best effort: offline, the last fetched origin/<base> is still worth reading.
    subprocess.run(["git", "-C", str(root), "fetch", "-q", "origin", base], timeout=120)
    return spec_files_at(root, f"origin/{base}")


def spec_gaps_or_warning(nodes: list[dict], base: str) -> list[dict]:
    """spec_gaps, or one gap saying the specs were not read: the sprint check goes on.

    Like spec_check.py's "issues not read", a gap only warns (Dolev's answer on #226).
    """
    try:
        files = repo_specs(base)
    except (ValueError, OSError, subprocess.TimeoutExpired) as err:
        return [{"path": None, "line": None, "message": f"spec files not read: {err}"}]
    return spec_gaps(nodes, files)


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
    parser.add_argument(
        "--spec", action="store_true", help="add spec_gaps (the specs on origin)"
    )
    args = parser.parse_args(argv)

    repo = args.repo or current_repo()
    nodes = open_issue_nodes(repo, with_body=True)
    sprint = args.milestone or current_sprint(nodes)
    if sprint is None:
        sys.exit("No open milestone has open issues.")
    base = api(f"repos/{repo}")["default_branch"]
    result = state(
        nodes,
        sprint,
        args.claimed,
        lambda pr: pr_status(repo, pr),
        lambda branch: branch_files(repo, base, branch),
        lambda number: pr_files(repo, number),
    )
    result |= pipeline_shas(CACHE)
    if args.spec:
        result["spec_gaps"] = spec_gaps_or_warning(nodes, base)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
