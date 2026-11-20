"""The merges Dolev declined in the orchestrator's permission window (S-2.18).

sprint_state.py marks each merge_queue entry with `declined`, from the comments
follow_ups.py already reads (one list call for the repo, never one per issue).

The orchestrator runs one merge per check, after its question window, and the merge's
permission window is the question. A check keeps no memory, so a decline is written on
the issue: an orchestrator comment (its `<!-- orchestrator -->` marker) with, on a line
of its own, `<!-- merge-declined: <sha> -->`, the head the merge call expected. That PR
comes up again only after a new head (a repair round pushed), or on Dolev's typed
request. A child's comment, or the same text from anyone else, never counts.
"""

import re

from follow_ups import issue_number
from watch_children import MARKER

DECLINED = re.compile(r"^<!--\s*merge-declined:\s*([0-9a-f]{7,40})\s*-->\s*$", re.M)


def declined_heads(comments: list[dict]) -> set[tuple[int, str]]:
    """(issue, head sha) of every merge an orchestrator comment says was declined."""
    return {
        (issue_number(c), sha)
        for c in comments
        if MARKER in (c.get("body") or "")
        for sha in DECLINED.findall(c.get("body") or "")
    }


def is_declined(declined: set[tuple[int, str]], number: int, head_sha: str) -> bool:
    """Whether the merge of `number` at `head_sha` was declined.

    A short sha in the marker matches the head it starts, so a hand-typed marker still
    counts; a different head (a repair round) never does.
    """
    return any(issue == number and head_sha.startswith(sha) for issue, sha in declined)
