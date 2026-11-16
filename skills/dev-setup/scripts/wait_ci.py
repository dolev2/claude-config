"""Waits until the CI of one pushed commit finishes, then prints the result and exits.

`dev-code` and `dev-spec` run it in the background (Bash with `run_in_background`)
right after a push, so its exit wakes the session, even one that already ended its
turn (claude-config #336). It replaces `gh pr checks --watch`, which needs GraphQL,
and `subscribe_pr_activity`, whose events belong to the session that merges.

    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/wait_ci.py" --sha "$(git rev-parse HEAD)"

The first line is one word, and the exit is 0 for all of them:
    success
    billing-flag <since> the billing flag is already on (S-1.54): no wait, and the
                         check runs are not read. A flag that could not be read is
                         a warning on stderr, and the ordinary wait
    failure              then one line per failed check: name, conclusion, html_url
    billing <html_url>   GitHub failed the check for billing; the billing flag is now
                         on (billing_flag.py, S-1.53). A second line
                         `not-written <reason>` when the flag could not be written
    timeout pending      some checks had not finished after --timeout
    timeout not-started  the repo has a pull_request workflow, but no check showed up
    none                 no workflow of the checkout runs on pull_request; no wait
    error                then gh's message: GitHub could not be read (a 403, or the
                         retries of gh_rest ran out), so the result is unknown
Bad input exits 2. "Green" is decided by `ci_summary`, as for the orchestrator.
"""

import argparse
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path

import billing_flag
from gh_rest import api_list, current_repo
from sprint_github import FAILED, billing_run, ci_summary

SHA = re.compile(r"[0-9a-f]{7,40}")
TOP_KEY = re.compile(r"^[\"']?([A-Za-z_][\w-]*)[\"']?\s*:(.*)$")
PR_EVENT = re.compile(r"\bpull_request(_target)?\b")


def sha_arg(text: str) -> str:
    """--sha: a commit hash, 7 to 40 hex characters."""
    if not SHA.fullmatch(text.strip().lower()):
        raise argparse.ArgumentTypeError(f"not a commit sha: {text}")
    return text.strip().lower()


def on_block(workflow: str) -> str:
    """The text of a workflow's top-level `on:` key, its value and indented lines.

    Read as text, not YAML: PyYAML is not installed everywhere this runs, and it
    reads a bare `on` as the boolean True.
    """
    lines, inside = [], False
    for line in workflow.splitlines():
        top = TOP_KEY.match(line)
        if top:
            inside = top.group(1) == "on"
            if inside:
                lines.append(top.group(2))
        elif inside:
            lines.append(line)
    return "\n".join(lines)


def has_pr_workflow(root: Path) -> bool:
    """True when a workflow under `root/.github/workflows` runs on pull requests."""
    folder = root / ".github" / "workflows"
    files = [*folder.glob("*.yml"), *folder.glob("*.yaml")] if folder.is_dir() else []
    return any(PR_EVENT.search(on_block(f.read_text(encoding="utf-8"))) for f in files)


def failed_lines(check_runs: list[dict]) -> list[str]:
    """One line per failed check: name, conclusion and link."""
    return [
        f"{run['name']} {run['conclusion']} {run.get('html_url', '')}".rstrip()
        for run in check_runs
        if run.get("conclusion") in FAILED
    ]


def wait(
    read_runs: Callable[[], list[dict]],
    interval: float,
    timeout: float,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    billing_of: Callable[[list[dict]], list[str] | None] = lambda runs: None,
) -> list[str]:
    """Poll the commit's check runs until they finish; the lines to print.

    `billing_of(runs)`: the lines of a billing failure, or None for an ordinary one.
    """
    deadline = clock() + timeout
    while True:
        runs = read_runs()
        summary = ci_summary(runs)
        if summary == "success":
            return ["success"]
        if summary == "failure":
            return billing_of(runs) or ["failure", *failed_lines(runs)]
        if clock() + interval > deadline:
            return ["timeout pending" if runs else "timeout not-started"]
        sleep(interval)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sha", type=sha_arg, required=True)
    parser.add_argument("--interval", type=float, default=30, help="seconds")
    parser.add_argument("--timeout", type=float, default=30 * 60, help="seconds")
    parser.add_argument(
        "--repo", help="owner/name; defaults to the repo of the current directory"
    )
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="the checkout; defaults to cwd"
    )
    args = parser.parse_args(argv)
    if args.interval <= 0 or args.timeout <= 0:
        parser.error("--interval and --timeout must be positive")

    if not has_pr_workflow(args.root):
        print("none")
        return
    flag = billing_flag.current()
    if flag is not None:
        print(f"billing-flag {flag['since']}")
        return
    repo = args.repo or current_repo()

    def read_runs() -> list[dict]:
        path = f"repos/{repo}/commits/{args.sha}/check-runs"
        return api_list(path, key="check_runs")

    def billing_of(runs: list[dict]) -> list[str] | None:
        url = billing_run(repo, runs)
        return None if url is None else billing_flag.billing_lines(url)

    try:
        lines = wait(read_runs, args.interval, args.timeout, billing_of=billing_of)
    except SystemExit as err:
        # gh_rest exits with gh's message on a failed call; an exit with no first
        # line would leave the session without a rule for it (claude-config #336).
        lines = ["error", str(err.code)]
    print("\n".join(lines))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
