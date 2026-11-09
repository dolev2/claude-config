"""Waits until an issue of an active child moves, then prints what moved and exits.

The sprint orchestrator runs it in the background (Bash with `run_in_background`), so
its exit wakes the orchestrator without a message from the child (claude-config #184:
the service raises a permission prompt on every `send_message` from a child).

    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/watch_children.py" --expect 184=explore,181=ready-to-execute \\
        --since 2026-11-08T15:00:00Z

Every round reads, for each issue in --expect, its status label and the comments created
after --since. The first round that finds a change prints one line per change and exits
0; so does a state that already differs at the start, which closes the gap between the
check that wrote --expect and this run. After --timeout it prints `timeout` and exits 0.
Bad input exits 2.

    #184 status explore -> waiting-approval
    #181 comment https://github.com/<repo>/issues/181#issuecomment-1

A comment the orchestrator wrote itself does not wake it: every comment is written from
Dolev's account, so there is no author to filter by, and the orchestrator opens each of
its comments with MARKER instead (claude-config #203).
"""

import argparse
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime

from gh_rest import api, api_list, current_repo

NO_STATUS = "none"
MARKER = "<!-- orchestrator -->"


def expect_map(text: str) -> dict[int, str]:
    """--expect: `N=status,...` (status without the `status:` prefix) as {N: status}."""
    expected = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        number, sep, status = part.partition("=")
        if not sep or not number.strip().isdigit() or not status.strip():
            raise argparse.ArgumentTypeError(f"not N=status: {part}")
        expected[int(number)] = status.strip()
    if not expected:
        raise argparse.ArgumentTypeError("no issues to watch")
    return expected


def iso_time(text: str) -> datetime:
    """--since: an ISO 8601 time with a zone, such as 2026-11-08T15:00:00Z."""
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as err:
        raise argparse.ArgumentTypeError(f"not an ISO time: {text}") from err
    if moment.tzinfo is None:
        raise argparse.ArgumentTypeError(f"no time zone: {text}")
    return moment


def status_of(issue: dict) -> str:
    """The issue's status label without its prefix, or `none`."""
    for label in issue.get("labels", []):
        name = label["name"]
        if name.startswith("status:"):
            return name.removeprefix("status:")
    return NO_STATUS


def new_comments(comments: list[dict], since: datetime) -> list[str]:
    """URLs of the comments created after `since`, without the orchestrator's own.

    The API's own `since` filters by update time, so an old comment edited later
    would pass it; the creation time decides here.
    """
    return [
        c["html_url"]
        for c in comments
        if datetime.fromisoformat(c["created_at"]) > since
        and MARKER not in (c.get("body") or "")
    ]


def changes(
    expected: dict[int, str],
    since: datetime,
    read_issue: Callable[[int], dict],
    read_comments: Callable[[int], list[dict]],
) -> list[str]:
    """One line per issue whose status moved and per comment created after `since`."""
    lines = []
    for number, status in expected.items():
        now = status_of(read_issue(number))
        if now != status:
            lines.append(f"#{number} status {status} -> {now}")
        lines += [
            f"#{number} comment {url}"
            for url in new_comments(read_comments(number), since)
        ]
    return lines


def watch(
    poll: Callable[[], list[str]],
    interval: float,
    timeout: float,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> list[str]:
    """Poll until a change shows up, then return it; `["timeout"]` after `timeout`."""
    deadline = clock() + timeout
    while True:
        found = poll()
        if found:
            return found
        if clock() + interval > deadline:
            return ["timeout"]
        sleep(interval)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--expect", type=expect_map, required=True)
    parser.add_argument("--since", type=iso_time, required=True)
    parser.add_argument("--interval", type=float, default=60, help="seconds")
    parser.add_argument("--timeout", type=float, default=25 * 60, help="seconds")
    parser.add_argument(
        "--repo", help="owner/name; defaults to the repo of the current directory"
    )
    args = parser.parse_args(argv)
    if args.interval <= 0 or args.timeout <= 0:
        parser.error("--interval and --timeout must be positive")

    repo = args.repo or current_repo()
    since = args.since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def poll() -> list[str]:
        return changes(
            args.expect,
            args.since,
            lambda n: api(f"repos/{repo}/issues/{n}"),
            lambda n: api_list(
                f"repos/{repo}/issues/{n}/comments?since={since}&per_page=100"
            ),
        )

    print("\n".join(watch(poll, args.interval, args.timeout)))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
