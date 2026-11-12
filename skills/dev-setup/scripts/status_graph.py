"""The blocking graph of the sprint, as a Mermaid block for /status (S-1.48).

work_status.py calls graph() with the open issues it already read, so the graph and the
tables come from the same picture and never disagree. Nothing here reads GitHub.

A node per open issue of the sprint, with its number, a short title and its status; an
arrow from each open blocker to the issue that waits for it. An open blocker outside the
sprint (another milestone, or another repo) is a dashed node. A closed blocker blocks
nothing, so it is left out.
"""

from collections.abc import Callable

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
    """One node: the number and short title, and the status under them."""
    name = f"{ref} · {label_text(title)}" if title else ref
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
    sprint_refs = {f"#{n['number']}" for n in in_sprint}
    lines = [
        node_line(f"#{n['number']}", n["title"], status_of(n, status_he))
        for n in in_sprint
    ]
    edges, outside = [], []
    for n in in_sprint:
        for ref in open_blockers(n):
            edges.append(f"  {node_id(ref)} --> {node_id('#' + str(n['number']))}")
            if ref not in sprint_refs and ref not in outside:
                outside.append(ref)
    for ref in outside:
        found = by_ref.get(ref)
        title, status = (
            (found["title"], status_of(found, status_he)) if found else ("", OTHER_REPO)
        )
        lines.append(node_line(ref, title, status))
    body = ["flowchart TD", *lines, *edges]
    if outside:
        body += [
            f"  {OUTSIDE_STYLE}",
            f"  class {','.join(map(node_id, outside))} outside",
        ]
    return f"{HEADING}\n\n```mermaid\n" + "\n".join(body) + "\n```"
