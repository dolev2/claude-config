"""The blocking graph of the sprint, as a Mermaid block for /status (S-1.48).

work_status.py calls graph() with the sprint's issues in the order of its table, and the
open issues it already read, so the graph and the tables come from the same picture and
never disagree. Nothing here reads GitHub.

A node per open issue of the sprint, with its number, a short title and its status; an
arrow from each open blocker to the issue that waits for it. An open blocker outside the
sprint (another milestone, or another repo) is a dashed node. A closed blocker blocks
nothing, so it is left out.
"""

import re
from collections.abc import Callable
from itertools import pairwise

from rank_issues import parse_issue

StatusHe = Callable[[str | None], str]

HEADING = "### גרף החסימות"
TITLE_LIMIT = 30
NO_SPRINT = "אין ספרינט פתוח."
EMPTY = "אין."
OTHER_REPO = "ריפו אחר"
OUTSIDE_STYLE = "classDef outside stroke-dasharray: 5 5"
# Mermaid reads #name; as an entity, and the label is HTML: these are written as codes.
LABEL_CODES = {"#": "#35;", '"': "#quot;", "<": "#lt;", ">": "#gt;", "&": "#amp;"}


def node_id(ref: str) -> str:
    """A Mermaid id for `#N` or `owner/name#N`: letters, digits and underscores only."""
    return "n" + "".join(c if c.isalnum() else "_" for c in ref.lstrip("#"))


def label_text(text: str, limit: int = TITLE_LIMIT) -> str:
    """The text cut to `limit` characters, safe inside a quoted Mermaid label.

    It is cut before the codes are written, so a cut never splits one.
    """
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return re.sub('[#"<>&]', lambda m: LABEL_CODES[m.group()], text)


def node_line(ref: str, title: str, status: str) -> str:
    """One node: the number, the short title and the status, each on its own line.

    The number has a line of its own so a Hebrew title never flips it to the far side.
    """
    name = f"{ref}<br>{label_text(title)}" if title else ref
    return f'  {node_id(ref)}["{name}<br>{status}"]'


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


def deepest(refs: list[str], edges: list[tuple[str, str]]) -> str:
    """The ref with the most blockers above it, so the next group starts below it all.

    Depth is relaxed at most len(refs) times, so a cycle of blockers still ends.
    """
    depth = dict.fromkeys(refs, 0)
    inside = [(a, b) for a, b in edges if a in depth and b in depth]
    for _ in refs:
        for a, b in inside:
            depth[b] = max(depth[b], min(depth[a] + 1, len(refs)))
    return max(reversed(refs), key=depth.__getitem__)


def stacking(groups: list[list[str]], edges: list[tuple[str, str]]) -> list[str]:
    """Invisible links that put each group under the one before it.

    The deepest node of a group links to every node of the next group that waits on
    nothing, so the next group starts below the whole group.
    """
    blocked = {b for _, b in edges}
    return [
        f"  {node_id(deepest(above, edges))} ~~~ {node_id(ref)}"
        for above, below in pairwise(groups)
        for ref in below
        if ref not in blocked
    ]


def node_status(ref: str, by_ref: dict[str, dict], status_he: StatusHe) -> str:
    """The status of a node, in the words of the tables.

    A blocker of another repo has none we read; one of this repo we did not read has
    no status either.
    """
    if "/" in ref:
        return OTHER_REPO
    found = by_ref.get(ref)
    return status_he(parse_issue(found).status if found else None)


def graph(
    sprint_nodes: list[dict] | None, nodes: list[dict], status_he: StatusHe
) -> str:
    """The graph section: a heading, then a Mermaid block or one line saying why not.

    `sprint_nodes` are the sprint's open issues in the table's order, None with no
    sprint. `nodes` are all the open issues of the repo, so a blocker in another
    milestone still shows its status.
    """
    if sprint_nodes is None:
        return f"{HEADING}\n\n{NO_SPRINT}"
    if not sprint_nodes:
        return f"{HEADING}\n\n{EMPTY}"
    by_ref = {f"#{n['number']}": n for n in nodes}
    issues = [parse_issue(n) for n in sprint_nodes]
    refs = [f"#{i.number}" for i in issues]
    edges = [
        (blocker, f"#{i.number}")
        for i in issues
        for blocker in [f"#{b}" for b in i.open_blockers] + i.outside_blockers
    ]
    outside = list(dict.fromkeys(b for b, _ in edges if b not in refs))
    lines = [
        node_line(
            ref,
            by_ref[ref]["title"] if ref in by_ref else "",
            node_status(ref, by_ref, status_he),
        )
        for ref in refs + outside
    ]
    lines += [f"  {node_id(a)} --> {node_id(b)}" for a, b in edges]
    lines += stacking(units(refs + outside, edges), edges)
    if outside:
        lines += [
            f"  {OUTSIDE_STYLE}",
            f"  class {','.join(map(node_id, outside))} outside",
        ]
    return f"{HEADING}\n\n```mermaid\nflowchart TD\n" + "\n".join(lines) + "\n```"
