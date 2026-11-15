"""The follow-up tasks children left in their hand-offs, not yet asked (S-2.16).

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a logged-in
`gh`; sprint_state.py adds its two keys to the orchestrator's picture:

    S="$HOME/.claude/skills/dev-setup/scripts"
    python "$S/follow_ups.py"                       # the current sprint
    python "$S/follow_ups.py" --milestone "Sprint 4"

A child never asks Dolev: its follow-up tasks stay under the fixed heading
`#### משימות המשך` of its hand-off comment (follow-ups.md, S-1.47), and the orchestrator
brings them to its window, one per window. The orchestrator keeps no memory between
checks and the child is archived by then, so what is still to ask is rebuilt from
GitHub every time:

1. The issues of the sprint's milestone, open and closed (a merge Dolev chose may close
   an issue before all its tasks were asked), and the repo's comments since the
   milestone was created: one list call each, never one per issue.
2. A hand-off is a comment without the orchestrator's marker that has the heading; every
   one of them counts (a repair round writes another).
3. Each top-level item under the heading, up to the next heading, is a task; its kind is
   its first bold word, `מוצר` or `תהליך`. "אין משימות המשך" is no tasks.
4. A task's key is the first 10 hex digits of the sha1 of its text, the list marker
   dropped and whitespace collapsed, so a task a repair round repeats is asked once.
5. Asked: the key appears as `<!-- follow-up: <key> -->` in an orchestrator comment on
   the same issue.

The keys, in the order of the comments:

    follow_ups       [{issue, pr, comment_url, kind, key, text}]: pr is the PR that
                     closes the issue, among the 100 PRs updated last, or null
    follow_up_gaps   [{issue, comment_url, message}], open issues only, each once: an
                     issue in status:in-review with no hand-off under the heading, a
                     heading with no task, or a task with no kind. The script never
                     guesses a kind
"""

import argparse
import hashlib
import json
import re
import sys

from gh_rest import api, closing_prs, current_repo, open_issue_nodes
from rank_issues import current_sprint
from watch_children import MARKER

PAGE = 100
HEADING = "#### משימות המשך"
NONE_LINE = "אין משימות המשך"
KINDS = ("מוצר", "תהליך")
ITEM = re.compile(r"^ {0,2}(?:\d+[.)]|[-*+])\s+")
HEADING_LINE = re.compile(r"^ {0,3}#{1,6}\s")
BOLD = re.compile(r"\*\*(.+?)\*\*")
ASKED = re.compile(r"<!--\s*follow-up:\s*([0-9a-f]{10})\s*-->")


def section(body: str) -> list[str] | None:
    """The lines under the heading, up to the next heading; None with no heading."""
    lines = body.replace("\r\n", "\n").split("\n")
    starts = [i for i, line in enumerate(lines) if line.strip() == HEADING]
    if not starts:
        return None
    found = []
    for line in lines[starts[0] + 1 :]:
        if HEADING_LINE.match(line):
            break
        found.append(line)
    return found


def items(lines: list[str]) -> list[str]:
    """Each top-level list item with its lines, the marker dropped.

    An item goes on in indented lines, and in the line after one that ends in `\\`.
    Any other line that is not indented ends the list, and with it the tasks: the
    hand-off goes on after it, maybe with a list of its own (the next step).
    """
    found: list[list[str]] = []
    previous = ""
    for line in lines:
        goes_on = line[:1].isspace() or previous.rstrip().endswith("\\")
        if ITEM.match(line):
            found.append([ITEM.sub("", line, count=1)])
        elif found and line.strip() and goes_on:
            found[-1].append(line.strip())
        elif found and line.strip():
            break
        previous = line
    texts = ["\n".join(item).strip() for item in found]
    return [text for text in texts if NONE_LINE not in text]


def kind_of(text: str) -> str | None:
    """The task's kind: its first bold word, when that is a kind."""
    match = BOLD.search(text)
    word = match.group(1).strip().rstrip(":").strip() if match else ""
    return word if word in KINDS else None


def task_key(text: str) -> str:
    """10 hex digits of the sha1 of the text, whitespace collapsed."""
    clean = " ".join(text.replace("\\", " ").split())
    return hashlib.sha1(clean.encode("utf-8")).hexdigest()[:10]


def issue_number(comment: dict) -> int:
    return int(comment["issue_url"].rstrip("/").rsplit("/", 1)[1])


def is_in_review(issue: dict) -> bool:
    labels = {label["name"] for label in issue.get("labels") or []}
    return issue.get("state") == "open" and "status:in-review" in labels


def hand_off(number: int, comment: dict) -> tuple[list[dict], list[dict]] | None:
    """(tasks, gaps) of one comment; None when it is not a hand-off."""
    body = comment.get("body") or ""
    lines = None if MARKER in body else section(body)
    if lines is None:
        return None
    url = comment.get("html_url")
    found = items(lines)
    if not found and NONE_LINE not in "\n".join(lines):
        return [], [gap(number, url, "בהערת המסירה יש כותרת בלי משימות")]
    tasks, gaps = [], []
    for text in found:
        kind = kind_of(text)
        if kind is None:
            gaps.append(gap(number, url, f"משימת המשך בלי סוג: {text[:60]}"))
            continue
        task = {"issue": number, "comment_url": url, "kind": kind}
        tasks.append(task | {"key": task_key(text), "text": text})
    return tasks, gaps


def asked_keys(comments: list[dict]) -> set[tuple[int, str]]:
    """(issue, key) of every task an orchestrator comment already asked about."""
    return {
        (issue_number(c), key)
        for c in comments
        if MARKER in (c.get("body") or "")
        for key in ASKED.findall(c.get("body") or "")
    }


def collect(issues: list[dict], comments: list[dict], pulls: list[dict]) -> dict:
    """follow_ups and follow_up_gaps, from the REST issues, comments and PRs."""
    numbers = {i["number"] for i in issues if "pull_request" not in i}
    is_open = {i["number"] for i in issues if i.get("state") == "open"}
    ours = [c for c in comments if issue_number(c) in numbers]
    seen = asked_keys(ours)
    tasks, gaps, handed_off = [], [], set()
    for comment in ours:
        number = issue_number(comment)
        read = hand_off(number, comment)
        if read is None:
            continue
        handed_off.add(number)
        found, missing = read
        # A closed issue's gap would come back every check; its tasks still count.
        known = {(g["issue"], g["message"]) for g in gaps}
        gaps += [
            g
            for g in missing
            if number in is_open and (g["issue"], g["message"]) not in known
        ]
        for task in found:
            if (number, task["key"]) in seen:
                continue
            seen.add((number, task["key"]))
            prs = closing_prs(number, pulls)
            tasks.append(task | {"pr": prs[0]["number"] if prs else None})
    for issue in issues:
        number = issue["number"]
        if number in numbers and is_in_review(issue) and number not in handed_off:
            gaps.append(gap(number, None, f"בהערת המסירה אין את הכותרת {HEADING}"))
    return {"follow_ups": tasks, "follow_up_gaps": gaps}


def gap(number: int, url: str | None, message: str) -> dict:
    return {"issue": number, "comment_url": url, "message": message}


def pages(path: str) -> list:
    """Every item of a REST list, page by page through `page=`.

    `gh api --paginate` follows GitHub's next links, which name the repository by id
    (`repositories/<id>/...`), and the cloud proxy refuses those (HTTP 403).
    """
    found: list = []
    for page in range(1, 1000):
        rows = api(f"{path}&per_page={PAGE}&page={page}")
        found += rows
        if len(rows) < PAGE:
            return found
    return found


def milestone_of(repo: str, title: str) -> dict:
    """The milestone named `title`, open or closed; exits when there is none."""
    for milestone in pages(f"repos/{repo}/milestones?state=all"):
        if milestone["title"] == title:
            return milestone
    sys.exit(f"No milestone named {title!r} in {repo}.")


def follow_ups(repo: str, sprint: str) -> dict:
    """The two keys for the milestone named `sprint`, read from GitHub."""
    milestone = milestone_of(repo, sprint)
    issues = pages(f"repos/{repo}/issues?milestone={milestone['number']}&state=all")
    # An issue carried in from an earlier sprint may have handed off before this one.
    since = min([milestone["created_at"]] + [i["created_at"] for i in issues])
    comments = pages(f"repos/{repo}/issues/comments?since={since}")
    # The 100 PRs updated last cover a sprint; every PR ever opened is not needed.
    pulls = api(
        f"repos/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=100"
    )
    return collect(issues, comments, pulls)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--milestone", help="defaults to the current sprint")
    parser.add_argument(
        "--repo", help="owner/name; defaults to the repo of the current directory"
    )
    args = parser.parse_args(argv)
    repo = args.repo or current_repo()
    sprint = args.milestone or current_sprint(open_issue_nodes(repo))
    if sprint is None:
        sys.exit("No open milestone has open issues.")
    print(json.dumps(follow_ups(repo, sprint), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
