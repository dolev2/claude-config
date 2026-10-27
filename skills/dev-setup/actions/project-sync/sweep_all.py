"""The scheduled board sync for every repo of one owner, run from a public repo.

Why this exists
---------------
A field edited by dragging a card raises no webhook (sync_project.py), so a poll every
15 minutes is the only thing that notices it. Run inside each private repo, that poll
used up the account's 2,000 free Actions minutes for October 2026, and with them CI in
every private repo. Runs in a public repo are free, so dolev2/.github runs this script
once for all of them (claude-config #46). Each repo's sync-project.yml keeps only the
issue events, which run when a label actually changes.

Which repos
-----------
Every repo of the owner with a PROJECT_NUMBER Actions variable, the same condition
sync-project.yml has. A new repo needs nothing more than dev-setup already sets.

What the log shows
------------------
The log of a public repo is public. So only counts are printed: no repo name, issue
number, status or sprint, not even on failure. A failed repo is "repo 3 of 6 failed",
and the run exits non-zero after every other repo has synced. To see what failed, run
this script locally with --verbose, which also prints each repo's name and output:

    GH_TOKEN=<token> python sweep_all.py --owner dolev2 --verbose
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SYNC_SCRIPT = Path(__file__).with_name("sync_project.py")
UPDATED_LINE = re.compile(r"^updated issues: (\d+)$", re.M)


def gh(*args: str) -> str:
    """Run the gh CLI and return its stdout; raise RuntimeError when it fails."""
    p = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip())
    return p.stdout


def list_repos(owner: str) -> list[str]:
    """The owner's repos that are not archived, as owner/name."""
    out = gh(
        "repo",
        "list",
        owner,
        "--no-archived",
        "--limit",
        "500",
        "--json",
        "nameWithOwner",
        "--jq",
        ".[].nameWithOwner",
    )
    return out.split()


def repo_variables(repo: str) -> dict[str, str]:
    """The repo's Actions variables, by name."""
    data = json.loads(gh("api", f"repos/{repo}/actions/variables?per_page=100"))
    return {v["name"]: v["value"] for v in data["variables"]}


def run_sync(repo: str, variables: dict[str, str]) -> subprocess.CompletedProcess:
    """Run sync_project.py over every issue of one repo, in quiet mode."""
    env = dict(os.environ)
    env.pop("ISSUE_NUMBER", None)  # no issue: a full sweep
    env.update(
        GITHUB_REPOSITORY=repo,
        PROJECT_NUMBER=variables["PROJECT_NUMBER"],
        SYNC_MARKER=variables.get("SYNC_MARKER", ""),
        SYNC_QUIET="1",
    )
    return subprocess.run(
        [sys.executable, str(SYNC_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def sync_one(repo: str, verbose: bool) -> int | None:
    """Issues updated in repo, or None when it has no board; raise when it fails."""
    variables = repo_variables(repo)
    if not variables.get("PROJECT_NUMBER", "").strip():
        return None
    result = run_sync(repo, variables)
    if verbose:
        print(f"--- {repo}\n{result.stdout}{result.stderr}")
    found = UPDATED_LINE.search(result.stdout)
    if result.returncode != 0 or not found:
        raise RuntimeError(f"sync exited with {result.returncode}")
    return int(found.group(1))


def main(argv: list[str] | None = None) -> int:
    """Sync every board of the owner; print counts only, exit 1 if any repo failed."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if not args.owner:
        parser.error("--owner is required outside GitHub Actions")

    try:
        repos = list_repos(args.owner)
    except RuntimeError as e:
        print("could not list the repos" + (f": {e}" if args.verbose else ""))
        return 1

    boards = updated = failed = 0
    for index, repo in enumerate(repos, 1):
        try:
            count = sync_one(repo, args.verbose)
        except RuntimeError as e:
            failed += 1
            print(f"repo {index} of {len(repos)} failed")
            if args.verbose:
                print(f"    {repo}: {e}")
            continue
        if count is not None:
            boards += 1
            updated += count

    print(
        f"repos: {len(repos)}, with a board: {boards + failed}, "
        f"issues updated: {updated}, failed: {failed}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
