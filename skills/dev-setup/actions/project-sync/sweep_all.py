"""The scheduled board sync for every repo of one owner, run from a public repo.

Why this exists
---------------
A card dragged on the board raises no webhook (sync_project.py), so a poll on an
hourly schedule, which GitHub runs a few times a day (claude-config #129), is what
puts it back in the column of its label, and catches up on an issue event whose run
failed. Run inside each private repo, that poll used up the account's
2,000 free Actions minutes for October 2026, and with them CI in every private repo.
Runs in a public repo are free, so dolev2/.github runs this script once for all of
them (claude-config #46). Each repo's sync-project.yml keeps only the
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

How many boards
---------------
A token that sees too few repos also sees too few boards, and the run would still be
green: on 2026-10-27 a wrong SYNC_BOARDS value saw 3 boards of 6, and three boards
stopped syncing unnoticed (claude-config #49). So the count is not derived through that
token. The EXPECTED_BOARDS Actions variable of dolev2/.github holds it, and a run that
finds any other number fails: fewer means boards went unsynced, more means the number
is out of date and would hide the next loss. In Actions the variable is required.
dev-setup sets it from a count made with Dolev's own token, which sees every repo:

    python sweep_all.py --owner dolev2 --count-boards

Active issues without a sprint
------------------------------
The run also prints how many open issues are in the pipeline (past backlog, short of
done) but have no milestone. dev-next scans only the current sprint, so nothing else
shows them (WayOut #42 and #117, claude-config #55). It is a count, never a failure: an
issue Dolev names may be planned outside every sprint. rank_issues.py names them.
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
WITHOUT_SPRINT_LINE = re.compile(r"^active without a sprint: (\d+)$", re.M)


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


REPOS_QUERY = """
query($owner: String!, $endCursor: String) {
  repositoryOwner(login: $owner) {
    repositories(first: 100, after: $endCursor, isArchived: false,
                 ownerAffiliations: OWNER) {
      nodes { nameWithOwner }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def repos_on_pages(owner: str, pages: list[dict]) -> list[str]:
    """owner/name of every repo on the GraphQL pages, owned by `owner` only."""
    return [
        repo["nameWithOwner"]
        for page in pages
        for repo in page["data"]["repositoryOwner"]["repositories"]["nodes"]
        if repo["nameWithOwner"].split("/", 1)[0].lower() == owner.lower()
    ]


def list_repos(owner: str) -> list[str]:
    """The owner's repos that are not archived, as owner/name, over every page.

    `gh repo list --limit 500` stopped at 500 repos (claude-config #164).
    """
    out = gh(
        "api",
        "graphql",
        "--paginate",
        "--slurp",
        "-f",
        f"query={REPOS_QUERY}",
        "-f",
        f"owner={owner}",
    )
    return repos_on_pages(owner, json.loads(out))


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


def sync_one(repo: str, verbose: bool) -> tuple[int, int] | None:
    """(issues updated, active issues without a sprint) in repo, or None when it has no
    board; raise when it fails."""
    variables = repo_variables(repo)
    if not variables.get("PROJECT_NUMBER", "").strip():
        return None
    result = run_sync(repo, variables)
    if verbose:
        print(f"--- {repo}\n{result.stdout}{result.stderr}")
    found = UPDATED_LINE.search(result.stdout)
    if result.returncode != 0 or not found:
        raise RuntimeError(f"sync exited with {result.returncode}")
    # Optional: the count is a warning, so a sync without it has not failed.
    without_sprint = WITHOUT_SPRINT_LINE.search(result.stdout)
    return int(found.group(1)), int(without_sprint.group(1)) if without_sprint else 0


def sweep(repos: list[str], verbose: bool) -> tuple[int, int, int, int]:
    """Sync each repo; return (boards found, issues updated, active issues without a
    sprint, repos failed)."""
    boards = updated = without_sprint = failed = 0
    for index, repo in enumerate(repos, 1):
        try:
            count = sync_one(repo, verbose)
        except RuntimeError as e:
            failed += 1
            print(f"repo {index} of {len(repos)} failed")
            if verbose:
                print(f"    {repo}: {e}")
            continue
        if count is not None:
            boards += 1
            updated += count[0]
            without_sprint += count[1]
    # A failed repo may have a board; counting it keeps a failure from also reading as
    # a missing board.
    return boards + failed, updated, without_sprint, failed


def expected_boards() -> int | None:
    """EXPECTED_BOARDS as a number; None when unset outside Actions; raise otherwise."""
    value = os.environ.get("EXPECTED_BOARDS", "").strip()
    if value.isdigit():
        return int(value)
    if value or os.environ.get("GITHUB_ACTIONS") == "true":
        raise ValueError("EXPECTED_BOARDS is not set")
    return None


def count_boards(repos: list[str]) -> int:
    """How many of repos have a PROJECT_NUMBER variable, without syncing any."""
    return sum(
        1 for repo in repos if repo_variables(repo).get("PROJECT_NUMBER", "").strip()
    )


def main(argv: list[str] | None = None) -> int:
    """Sync every board of the owner; print counts only, exit 1 on any failure."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--owner", default=os.environ.get("GITHUB_REPOSITORY_OWNER"))
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--count-boards", action="store_true")
    args = parser.parse_args(argv)
    if not args.owner:
        parser.error("--owner is required outside GitHub Actions")

    try:
        expected = None if args.count_boards else expected_boards()
        repos = list_repos(args.owner)
        if args.count_boards:
            print(count_boards(repos))
            return 0
    except ValueError as e:
        print(e)
        return 1
    except RuntimeError as e:
        print("could not read the repos" + (f": {e}" if args.verbose else ""))
        return 1

    found, updated, without_sprint, failed = sweep(repos, args.verbose)
    print(
        f"repos: {len(repos)}, with a board: {found}, "
        f"issues updated: {updated}, failed: {failed}"
    )
    # A count, never a failure (see "Active issues without a sprint" above).
    print(f"active issues without a sprint: {without_sprint}")
    if expected is not None and found != expected:
        print(f"expected boards: {expected}, found: {found}")
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
