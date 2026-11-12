"""Says whether an issue is paused, and why, before work on it starts (S-1.44).

Usage:
    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/pause_reason.py" 42
    python "$S/pause_reason.py" 42 --repo owner/name

Prints `not paused`, or `paused` and, on the next line, the reason: the text of the
newest comment that starts with `סיבת השהיה:` (leading spaces allowed), without the
prefix. No such comment: `paused` alone. dev-plan, dev-code and dev-next all ask the
same question (../reference/chat-decisions.md), so the reading lives here, once.
Reads through gh_rest.py, so it works in a cloud session too.
"""

import argparse
import sys

from gh_rest import api, api_list, current_repo

LABEL = "paused"
PREFIX = "סיבת השהיה:"


def is_paused(issue: dict) -> bool:
    """True when the REST issue carries the `paused` label."""
    return any(label.get("name") == LABEL for label in issue.get("labels", []))


def latest_reason(comments: list[dict]) -> str | None:
    """The reason in the newest comment that starts with the prefix, or None.

    `comments` are REST issue comments, oldest first (the order GitHub returns them).
    A comment that only mentions the prefix in its middle is not a reason.
    """
    for comment in reversed(comments):
        body = (comment.get("body") or "").lstrip()
        if body.startswith(PREFIX):
            return body[len(PREFIX) :].strip()
    return None


def report(issue: dict, comments: list[dict]) -> str:
    """The lines to print for one issue and its comments."""
    if not is_paused(issue):
        return "not paused"
    reason = latest_reason(comments)
    return f"paused\n{reason}" if reason else "paused"


def issue_number(text: str) -> int:
    """The issue number from `42` or `#42`; argparse turns a ValueError into exit 2."""
    number = int(text.lstrip("#"))
    if number <= 0:
        raise ValueError(text)
    return number


def main(argv: list[str]) -> int:
    """Prints the pause state of the issue named in argv; returns the exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("number", type=issue_number, help="the issue number")
    parser.add_argument(
        "--repo", help="owner/name; defaults to the repo of the current directory"
    )
    args = parser.parse_args(argv)
    repo = args.repo or current_repo()
    issue = api(f"repos/{repo}/issues/{args.number}")
    comments = (
        api_list(f"repos/{repo}/issues/{args.number}/comments?per_page=100")
        if is_paused(issue)
        else []
    )
    print(report(issue, comments))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
