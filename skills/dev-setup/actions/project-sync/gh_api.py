"""The one door to GitHub for the board sync: the gh CLI and GraphQL through it.

Every other module calls gh() and graphql() through this module (gh_api.gh, not a
from-import), so a test replaces them in one place.
"""

import json
import re
import subprocess
import time

# A 502/503/504 from GitHub passes within seconds, and one used to fail the whole run
# and mail (claude-config #105). Retrying is safe because every call the sync makes is
# idempotent: a read, a field set to a value, labels set to a list, or an add that
# tolerates an issue already on the board.
RETRY_WAITS = (2, 5)
TRANSIENT = re.compile(r"HTTP 50[234]")


def run_gh(args: tuple[str, ...]) -> subprocess.CompletedProcess:
    """One run of the gh CLI, its output captured as text."""
    return subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def gh(*args: str) -> str:
    """Run the gh CLI and return its stdout; raise RuntimeError when it fails.

    A transient server error is tried again after each of RETRY_WAITS seconds; any
    other failure raises at once.
    """
    for wait in RETRY_WAITS:
        p = run_gh(args)
        if p.returncode == 0 or not TRANSIENT.search(p.stderr):
            break
        time.sleep(wait)
    else:
        p = run_gh(args)
    if p.returncode != 0:
        raise RuntimeError(
            "gh {} failed: {}".format(" ".join(args[:3]), p.stderr.strip())
        )
    return p.stdout


def graphql(query: str, **variables: str | int) -> dict:
    """Run a GraphQL query through gh and return the parsed response."""
    args = ["api", "graphql", "-f", "query=" + query]
    for k, v in variables.items():
        # -F turns anything that looks like a number into one, and an option id can be
        # all digits ("84237580"), which GitHub then rejects as a String!.
        # Only ints get -F.
        flag = "-F" if isinstance(v, int) else "-f"
        args += [flag, f"{k}={v}"]
    out = json.loads(gh(*args))
    # A GraphQL error can arrive with a 200, which gh reports as success. Without this
    # check a failed mutation looks like a successful sync.
    if out.get("errors"):
        raise RuntimeError(json.dumps(out["errors"], ensure_ascii=False)[:800])
    return out
