"""Compares a spec between two refs: which parts are new, changed or deleted (#244).

After a spec PR merges, dev-ship lists what the change means for the open issues
(spec_check.py --changes): a deleted part closes its issue as not planned, a changed
part sends an issue that is still before the code back to planning, and an issue
already in the code or in review waits for Dolev (S-1.34).

What counts as a change: the part's heading name and its text, up to the next heading
at its level or above, or the next part. Its status line and "שופר ב-#N" do not
count: they say who built the part, not what it is.
"""

import re
from typing import NamedTuple

from spec_parse import HEADING, PART_ID, STATUS_LIKE

IMPROVED = r"שופר ב-#\d+(?:\s*,\s*#\d+)*"
IMPROVED_IN_PARENS = re.compile(r"\s*\(" + IMPROVED + r"\)")
IMPROVED_BARE = re.compile(r"[,;]?\s*" + IMPROVED)
BEFORE_CODE = {
    "status:explore",
    "status:plan-questions",
    "status:waiting-approval",
    "status:ready-to-execute",
}


class Change(NamedTuple):
    """A part that is new, changed or deleted; `name` is its newest name."""

    kind: str
    path: str
    id: str
    name: str


def part_texts(text: str) -> dict[str, tuple[str, list[str]]]:
    """{part id: (name, the lines under its heading)} of one spec file.

    A heading inside a ``` block is an example, not a boundary; its lines still
    belong to the part. A duplicate id keeps its first part (spec_check flags it).
    """
    found: dict[str, tuple[str, list[str]]] = {}
    current: list[str] | None = None
    level = 0
    in_fence = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        heading = None if in_fence else HEADING.match(line)
        if heading:
            depth, title = len(heading[1]), heading[2]
            part = PART_ID.match(title)
            if part or depth <= level:
                current, level = None, 0
            if part and f"S-{part[1]}.{part[2]}" not in found:
                current, level = [], depth
                found[f"S-{part[1]}.{part[2]}"] = ((part[3] or "").strip(), current)
                continue
        if current is not None:
            current.append(line)
    return found


def normalized(lines: list[str]) -> str:
    """A part's text without what does not count: status line, "שופר ב-", spacing."""
    body = [line.rstrip() for line in lines]
    first = next((i for i, line in enumerate(body) if line.strip()), None)
    if first is not None and STATUS_LIKE.match(body[first].strip()):
        del body[first]
    kept: list[str] = []
    for line in body:
        line = IMPROVED_BARE.sub("", IMPROVED_IN_PARENS.sub("", line)).rstrip()
        if line or (kept and kept[-1]):
            kept.append(line)
    return "\n".join(kept).strip("\n")


def compare(old: dict[str, str], new: dict[str, str]) -> list[Change]:
    """The parts that differ between two {path: text}: new and changed, then deleted.

    The key is (path, id): a part that moved to another file is deleted from one
    and new in the other.
    """
    changes = []
    old_parts = {path: part_texts(text) for path, text in old.items()}
    new_parts = {path: part_texts(text) for path, text in new.items()}
    for path, parts in new_parts.items():
        before = old_parts.get(path, {})
        for part_id, (name, lines) in parts.items():
            if part_id not in before:
                changes.append(Change("new", path, part_id, name))
                continue
            old_name, old_lines = before[part_id]
            if name != old_name or normalized(lines) != normalized(old_lines):
                changes.append(Change("changed", path, part_id, name))
    for path, parts in old_parts.items():
        after = new_parts.get(path, {})
        for part_id, (name, _) in parts.items():
            if part_id not in after:
                changes.append(Change("deleted", path, part_id, name))
    return changes


def action(kind: str, labels: set[str]) -> str | None:
    """What happens to an open issue of a part: close, explore or ask (S-1.34).

    None for a new part: no issue to update, the part goes to the breakdown.
    """
    if kind == "deleted":
        return "close"
    if kind == "changed":
        return "explore" if labels & BEFORE_CODE else "ask"
    return None


def status_label(labels: set[str]) -> str:
    """The issue's status: label, or "no status" when it has none."""
    found = sorted(label for label in labels if label.startswith("status:"))
    return found[0] if found else "no status"


def report(
    changes: list[Change], pointed: dict[tuple[str, str], list[dict]] | None
) -> list[str]:
    """The lines of `--changes`: a line per part, a line per open issue under it.

    `pointed` is {(path, id): open issues} (spec_check.pointers); None: the issues
    were not read, so only the parts are listed. A new part that an issue already
    points at is left out: the breakdown does not need it.
    """
    lines = []
    for change in changes:
        issues = [] if pointed is None else pointed.get((change.path, change.id), [])
        if change.kind == "new" and issues:
            continue
        lines.append(f"{change.kind} {change.id} · {change.name}")
        if change.kind == "new":
            continue
        for issue in sorted(issues, key=lambda found: found["number"]):
            todo = action(change.kind, issue["labels"])
            label = status_label(issue["labels"])
            lines.append(f"  #{issue['number']} {label} -> {todo}")
    return lines or ["no spec changes"]
