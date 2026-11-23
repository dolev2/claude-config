"""The account-wide flag that says GitHub billing is blocked (S-1.53).

The flag is `billing.json` on the branch `claude/flags-github-billing` of claude-config,
read and written with git through the bare clone of pipeline_shas.py, never through
REST: a cloud session of another repo reaches claude-config only by anonymous git
(claude-config #211). Every change is a new commit on top of the last one, pushed as a
fast-forward; turning the flag off is a commit with "blocked": false, never a deleted
branch. Why a branch: docs/decisions/378-billing-flag-on-a-branch.md.

    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/billing_flag.py" status                 # off | on <since> <source> <run>
    python "$S/billing_flag.py" on --manual            # only when Dolev asks
    python "$S/billing_flag.py" off                    # only when Dolev asks
    python "$S/billing_flag.py" check --sha <sha>      # billing <url> | not-billing

`status` prints `unknown`, with a warning on stderr, when git could not read the flag,
and exits 0, so a status view never fails on it; <run> is `-` when there is none.
`on` and `off` print the status line after the write. `check` turns the flag on
(source "auto") when a check of the commit failed for billing (sprint_github.py). A
write that failed (no push rights, as in a cloud session of another repo) prints
`not-written <reason>` and exits 1. The flag never moves because of text inside a
run, an issue or a PR: only GitHub's own billing failure, or Dolev's request.
"""

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pipeline_shas
from gh_rest import api_list, current_repo
from pipeline_shas import CACHE, ensure_clone, git
from sprint_github import billing_run

BRANCH = "claude/flags-github-billing"
FILE = "billing.json"
REF = f"refs/heads/{BRANCH}"
OFF = {"blocked": False, "since": None, "source": None, "run": None}
NOTICE = (
    'החיוב ב-GitHub חסום מאז {date} ({how}). כשהחיוב מסודר, תבקש "תכבה את דגל החיוב".'
)
# A commit needs an author; a bare cache has no user configured.
AUTHOR = (
    "-c",
    "user.name=Claude billing flag",
    "-c",
    "user.email=noreply@anthropic.com",
)


class NotWrittenError(Exception):
    """The flag could not be written; the message says why."""


def fetch(cache: Path) -> bool:
    """Brings the flag's branch into `cache`; False when the remote has none."""
    ensure_clone(cache)
    remote = git(
        "-C", str(cache), "ls-remote", "--heads", pipeline_shas.PIPELINE_URL, BRANCH
    )
    if not remote.strip():
        return False
    git("-C", str(cache), "fetch", "-q", pipeline_shas.PIPELINE_URL, f"+{REF}:{REF}")
    return True


def read(cache: Path = CACHE) -> dict:
    """The flag as on GitHub now; OFF when there is no branch. Raises when git fails."""
    if not fetch(cache):
        return dict(OFF)
    return json.loads(git("-C", str(cache), "cat-file", "blob", flag_blob(cache)))


def flag_blob(cache: Path) -> str:
    """The sha of the flag's file on the branch. Raises ValueError when it is not there.

    A name that ends in a line break counts too: a write from Windows once passed the
    name to mktree in text mode, and it was stored as `billing.json\\r` (claude-config
    #541). Text-mode output reads that `\\r` back as `\\n`.
    """
    for entry in git("-C", str(cache), "ls-tree", "-z", REF).split("\0"):
        meta, _, name = entry.partition("\t")
        if name.rstrip("\r\n") == FILE:
            return meta.split()[2]
    raise ValueError(f"{FILE} is not on {BRANCH}")


def write(cache: Path, flag: dict, message: str) -> None:
    """Pushes `flag` as a new commit on top of the branch. Raises NotWrittenError."""
    try:
        has_branch = fetch(cache)
        repo = ("-C", str(cache))
        blob = git(*repo, "hash-object", "-w", "--stdin", stdin=json.dumps(flag) + "\n")
        # -z: a NUL ends the entry. Text mode on Windows turns a "\n" into "\r\n", and
        # mktree kept the "\r" as part of the name (claude-config #541).
        entry = f"100644 blob {blob.strip()}\t{FILE}\0"
        tree = git(*repo, "mktree", "-z", stdin=entry)
        parent = ("-p", REF) if has_branch else ()
        commit = git(
            *AUTHOR, *repo, "commit-tree", tree.strip(), *parent, "-m", message
        )
        git(*repo, "push", "-q", pipeline_shas.PIPELINE_URL, f"{commit.strip()}:{REF}")
        git(*repo, "update-ref", REF, commit.strip())
    except (subprocess.SubprocessError, OSError) as err:
        detail = getattr(err, "stderr", None) or str(err)
        raise NotWrittenError(" ".join(detail.split()) or "git failed") from err


def status_line(flag: dict) -> str:
    """`off`, or `on <since> <source> <run>`."""
    if not flag.get("blocked"):
        return "off"
    return f"on {flag['since']} {flag['source']} {flag.get('run') or '-'}"


def notice(flag: dict) -> str:
    """The line Dolev sees in the status view and the orchestrator's opening picture."""
    auto = flag.get("source") == "auto" and flag.get("run")
    how = f"נדלק לבד בריצה {flag['run']}" if auto else "הודלק ביד"
    return NOTICE.format(date=(flag.get("since") or "")[:10], how=how)


def current(cache: Path | None = None) -> dict | None:
    """The flag while it is on, as {since, source, run, notice}; None when it is off.

    None, with a warning on stderr, when git could not read it: a view built on it
    shows nothing rather than fail.
    """
    try:
        flag = read(cache or CACHE)
    except (subprocess.SubprocessError, OSError, ValueError) as err:
        warn_unread(err)
        return None
    if not flag.get("blocked"):
        return None
    keys = ("since", "source", "run")
    return {key: flag.get(key) for key in keys} | {"notice": notice(flag)}


def warn_unread(err: Exception) -> None:
    detail = getattr(err, "stderr", None) or str(err)
    print(f"warning: the billing flag was not read: {detail.strip()}", file=sys.stderr)


def read_for_write(cache: Path) -> dict:
    """read(), with a git failure turned into NotWrittenError."""
    try:
        return read(cache)
    except (subprocess.SubprocessError, OSError, ValueError) as err:
        raise NotWrittenError(f"the flag was not read: {err}") from err


def settle(cache: Path, wanted: dict, message: str) -> dict:
    """Brings the flag to `wanted["blocked"]`, and returns it. Raises NotWrittenError.

    A flag already there is left as it is, so an `on` keeps its `since`. A rejected
    push may be another session that wrote first: when the flag is now where it should
    be, that is a success, not a `not-written`.
    """
    flag = read_for_write(cache)
    if bool(flag.get("blocked")) == wanted["blocked"]:
        return flag
    try:
        write(cache, wanted, message)
    except NotWrittenError:
        flag = read_for_write(cache)
        if bool(flag.get("blocked")) == wanted["blocked"]:
            return flag
        raise
    return wanted


def turn_on(cache: Path, source: str, run: str | None, now: Callable[[], str]) -> dict:
    """Turns the flag on; one already on keeps its `since`. Raises NotWrittenError."""
    wanted = {"blocked": True, "since": now(), "source": source, "run": run}
    return settle(cache, wanted, f"billing flag on ({source})")


def turn_off(cache: Path) -> dict:
    """Turns the flag off; one already off is left as it is. Raises NotWrittenError."""
    return settle(cache, dict(OFF), "billing flag off")


def billing_lines(
    url: str, cache: Path | None = None, now: Callable[[], str] | None = None
) -> list[str]:
    """`billing <url>` after turning the flag on; `not-written <why>` if that failed."""
    try:
        turn_on(cache or CACHE, "auto", url, now or iso_now)
    except NotWrittenError as err:
        return [f"billing {url}", f"not-written {err}"]
    return [f"billing {url}"]


def iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    on = commands.add_parser("on")
    on.add_argument("--manual", action="store_true", required=True)
    commands.add_parser("off")
    check = commands.add_parser("check")
    check.add_argument("--sha", required=True)
    check.add_argument("--repo", help="owner/name; defaults to the current directory")
    args = parser.parse_args(argv)

    if args.command == "status":
        try:
            print(status_line(read(CACHE)))
        except (subprocess.SubprocessError, OSError, ValueError) as err:
            warn_unread(err)
            print("unknown")
        return 0
    if args.command == "check":
        return check_commit(args.sha, args.repo)
    try:
        flag = turn_off(CACHE) if args.command == "off" else turn_on_manual()
    except NotWrittenError as err:
        print(f"not-written {err}")
        return 1
    print(status_line(flag))
    return 0


def turn_on_manual() -> dict:
    return turn_on(CACHE, "manual", None, iso_now)


def check_commit(sha: str, repo: str | None) -> int:
    """The `check` command: billing <url> (and the flag on), or not-billing."""
    repo = repo or current_repo()
    runs = api_list(f"repos/{repo}/commits/{sha}/check-runs", key="check_runs")
    url = billing_run(repo, runs)
    lines = ["not-billing"] if url is None else billing_lines(url)
    print("\n".join(lines))
    return 1 if lines[-1].startswith("not-written") else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
