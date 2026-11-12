"""The blocking graph of the sprint, as a Mermaid block for /status (S-1.48).

work_status.py calls graph() with the open issues it already read, so the graph and the
tables come from the same picture and never disagree. Nothing here reads GitHub.

A node per open issue of the sprint, with its number, a short title and its status; an
arrow from each open blocker to the issue that waits for it. An open blocker outside the
sprint (another milestone, or another repo) is a dashed node. A closed blocker blocks
nothing, so it is left out.
"""

from collections.abc import Callable
from itertools import pairwise

from rank_issues import is_local, label_value, outside_ref

StatusHe = Callable[[str | None], str]

HEADING = "### גרף החסימות"
TITLE_LIMIT = 30
NO_SPRINT = "אין ספרינט פתוח."
EMPTY = "אין."
OTHER_REPO = "ריפו אחר"
OUTSIDE_STYLE = "classDef outside stroke-dasharray: 5 5"


def node_id(ref: str) -> str:
    """A Mermaid id for `#N` or `owner/name#N`: letters, digits and underscores only."""
    return "n" + "".join(c if c.isalnum() else "_" for c in ref.lstrip("#"))


def label_text(text: str, limit: int = TITLE_LIMIT) -> str:
    """The text cut to `limit` characters, safe inside a quoted Mermaid label."""
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text.replace('"', "#quot;")


def node_line(ref: str, title: str, status: str) -> str:
    """One node: the number, the short title and the status, each on its own line.

    The number has a line of its own so a Hebrew title never flips it to the far side.
    """
    name = f"{ref}<br>{label_text(title)}" if title else ref
    return f'  {node_id(ref)}["{name}<br>{status}"]'


def status_of(node: dict, status_he: StatusHe) -> str:
    """The node's status, in the words of the tables."""
    labels = [label["name"] for label in node["labels"]["nodes"]]
    return status_he(label_value(labels, "status:"))


def open_blockers(node: dict) -> list[str]:
    """The node's open blockers, as `#N` or `owner/name#N`."""
    return [
        f"#{b['number']}" if is_local(b) else outside_ref(b)
        for b in node["blockedBy"]["nodes"]
        if b["state"] == "OPEN"
    ]


def units(refs: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """The refs in groups to stack one under another, so the graph grows downward.

    A group is a connected chain of blockers, in the order of `refs`. Issues with no
    arrow at all go two to a group, so they sit in pairs rather than in one long row.
    """
    group = {ref: ref for ref in refs}

    def root(ref: str) -> str:
        while group[ref] != ref:
            ref = group[ref]
        return ref

    for a, b in edges:
        group[root(a)] = root(b)
    linked = {ref for edge in edges for ref in edge}
    chains: dict[str, list[str]] = {}
    for ref in refs:
        if ref in linked:
            chains.setdefault(root(ref), []).append(ref)
    alone = [ref for ref in refs if ref not in linked]
    return list(chains.values()) + [alone[i : i + 2] for i in range(0, len(alone), 2)]


def stacking(groups: list[list[str]], edges: list[tuple[str, str]]) -> list[str]:
    """Invisible links that put each group under the one before it.

    The last node of a group (one nothing waits on) links to every node of the next
    group that waits on nothing, so the next group starts below it.
    """
    blocked = {b for _, b in edges}
    blocking = {a for a, _ in edges}
    lines = []
    for above, below in pairwise(groups):
        # A cycle of blockers has no such node: its last one stands in.
        ends = [ref for ref in above if ref not in blocking] or above
        bottom = ends[-1]
        lines += [
            f"  {node_id(bottom)} ~~~ {node_id(ref)}"
            for ref in below
            if ref not in blocked
        ]
    return lines


def graph(nodes: list[dict], sprint: str | None, status_he: StatusHe) -> str:
    """The graph section: a heading, then a Mermaid block or one line saying why not.

    `nodes` are all the open issues of the repo, so a blocker in another milestone
    still shows its status. `status_he` turns a status label into the tables' words.
    """
    if sprint is None:
        return f"{HEADING}\n\n{NO_SPRINT}"
    in_sprint = [
        n for n in nodes if n["milestone"] and n["milestone"]["title"] == sprint
    ]
    if not in_sprint:
        return f"{HEADING}\n\n{EMPTY}"
    by_ref = {f"#{n['number']}": n for n in nodes}
    refs = [f"#{n['number']}" for n in in_sprint]
    edges = [(b, f"#{n['number']}") for n in in_sprint for b in open_blockers(n)]
    outside = list(dict.fromkeys(b for b, _ in edges if b not in refs))
    lines = []
    for ref in refs + outside:
        found = by_ref.get(ref)
        title, status = (
            (found["title"], status_of(found, status_he)) if found else ("", OTHER_REPO)
        )
        lines.append(node_line(ref, title, status))
    lines += [f"  {node_id(a)} --> {node_id(b)}" for a, b in edges]
    lines += stacking(units(refs + outside, edges), edges)
    if outside:
        lines += [
            f"  {OUTSIDE_STYLE}",
            f"  class {','.join(map(node_id, outside))} outside",
        ]
    return f"{HEADING}\n\n```mermaid\nflowchart TD\n" + "\n".join(lines) + "\n```"
