"""Which sessions belong to which issue, for /status (S-1.50, S-1.57).

The status skill writes every row `list_sessions` returned, as it is, to a JSON file:
`[{id, title, tags, session_status, created_at}, ...]`. This module turns that list into
`{issue: [{url, title, created_at}, ...]}`, the shape the page and the tables read, so
the rule of what an issue's session is lives here and not in the skill.

A session belongs to issue N of the repo when it is not archived, carries no `repo:` tag
of another repo, and either has the tags `repo:<owner>/<name>` and `issue:<N>`, or is
named `<name>: claude/issue-<N>-<slug>` (the session title of git-flow.md), so a session
opened by hand, with no tags, still counts.
"""

import json
import re
import sys
from pathlib import Path

ARCHIVED = "SESSION_STATUS_ARCHIVED"
SESSION_URL = "https://claude.ai/code/{id}"
ACTIVE_MARK = " · פעיל"

Sessions = dict[int, list[dict]]


def issue_of(row: dict, repo: str) -> int | None:
    """The issue of `repo` that the session row works on, or None.

    The tags win when they name this repo; otherwise the session's name decides.
    """
    if row.get("session_status") == ARCHIVED:
        return None
    tags = [tag for tag in row.get("tags") or [] if isinstance(tag, str)]
    repos = {tag[len("repo:") :].lower() for tag in tags if tag.startswith("repo:")}
    if repos and repos != {repo.lower()}:
        return None
    if repos:
        for tag in tags:
            if re.fullmatch(r"issue:\d+", tag):
                return int(tag.split(":")[1])
    name = re.escape(repo.split("/")[-1])
    found = re.match(rf"{name}: claude/issue-(\d+)-", row.get("title") or "", re.I)
    return int(found.group(1)) if found else None


def by_issue(rows: list[dict], repo: str) -> Sessions:
    """{issue: [{url, title, created_at}]} for the rows that belong to an issue."""
    sessions: Sessions = {}
    for row in rows:
        number = issue_of(row, repo)
        if number is not None:
            sessions.setdefault(number, []).append(
                {
                    "url": SESSION_URL.format(id=row["id"]),
                    "title": row.get("title") or "",
                    "created_at": row.get("created_at"),
                }
            )
    return sessions


def read_sessions(path: str, repo: str) -> Sessions:
    """The sessions file, as by_issue() of its rows.

    Exits 2 with what is wrong, so a broken file never shows as "no sessions".
    """
    try:
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("not a list of sessions")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                raise ValueError(f"a session without an id: {row!r}")
            if not isinstance(row.get("title") or "", str):
                raise ValueError(f"a session whose title is not text: {row!r}")
            if not isinstance(row.get("tags") or [], list):
                raise ValueError(f"a session whose tags are not a list: {row!r}")
        return by_issue(rows, repo)
    except (OSError, ValueError) as error:
        print(f"קובץ הסשנים {path} לא נקרא: {error}", file=sys.stderr)
        sys.exit(2)
