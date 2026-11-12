"""The clickable blocking graph of /status, as one HTML page (S-1.50).

work_status.py --page writes it from the same layout as the chat graph
(status_graph.layout), so the page and the chat never disagree. The status skill then
publishes it to the repo's one fixed page. Nothing here reads GitHub or the sessions:
the PRs come from the issue nodes, and the sessions are passed in.

On each node, under its status, up to three kinds of link: the issue (always), its
open PR (when there is one), and each session of the issue that is not archived.
"""

import html
import json
from collections.abc import Callable

from status_graph import EMPTY, NO_SPRINT, mermaid_lines

PAGE_TITLE = "גרף החסימות · {name}"
SESSIONS_NOT_READ = "רשימת הסשנים לא נקראה, ולכן אין קישורי סשן."
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
ISSUE_WORD = "משימה"
PR_WORD = "PR"
SESSION_WORD = "סשן"

Sessions = dict[int, list[dict]]


def page_title(repo: str) -> str:
    """The fixed name of the repo's page: the skill finds the page by it."""
    return PAGE_TITLE.format(name=repo.split("/")[-1])


def session_order(entries: list[dict]) -> list[dict]:
    """The sessions of one issue in the order their links appear on the node."""
    # TODO(human): return `entries` newest first (S-1.50: "מהחדש לישן"), by each
    # entry's "created_at" (an ISO 8601 string). Decide what happens to an entry
    # without "created_at". Don't change the list you were given.
    return entries


def link(url: str, word: str) -> str:
    """One small link, safe inside a quoted Mermaid label.

    Single quotes around the URL, since the label itself is in double quotes; the URL
    and the word are escaped so neither can close the label or the tag.
    """
    safe = html.escape(url, quote=True).replace("#", "%23")
    return f"<a class='lnk' href='{safe}' target='_blank' rel='noopener'>{word}</a>"


def node_links(
    repo: str, prs: dict[str, list[int]], sessions: Sessions | None
) -> Callable[[str], str]:
    """For a ref, the links that go under its status on the page."""

    def links(ref: str) -> str:
        if "/" in ref:
            owner_repo, number = ref.split("#")
            return link(f"https://github.com/{owner_repo}/issues/{number}", ISSUE_WORD)
        number = int(ref.lstrip("#"))
        parts = [link(f"https://github.com/{repo}/issues/{number}", ISSUE_WORD)]
        parts += [
            link(f"https://github.com/{repo}/pull/{pr}", f"{PR_WORD} {pr}")
            for pr in prs.get(ref, [])
        ]
        for index, entry in enumerate(session_order((sessions or {}).get(number, []))):
            word = SESSION_WORD if index == 0 else f"{SESSION_WORD} {index + 1}"
            parts.append(link(entry["url"], word))
        return " · ".join(parts)

    return links


def open_prs(nodes: list[dict]) -> dict[str, list[int]]:
    """The open PRs that close each issue, as `#N` → [PR numbers]."""
    return {
        f"#{n['number']}": [pr["number"] for pr in n.get("closingPullRequests") or []]
        for n in nodes
    }


def page(
    repo: str,
    shape: dict | None,
    nodes: list[dict],
    sessions: Sessions | None,
    updated: str,
) -> str:
    """The whole page. `shape` is a status_graph.layout(), or None with no sprint.

    A sprint with no open issue has an empty layout; both cases show the chat's line
    instead of a graph. `sessions` is None when the list was not read.
    """
    notes = [f"עודכן: {html.escape(updated)}"]
    if sessions is None:
        notes.append(SESSIONS_NOT_READ)
    if shape is None or not shape["refs"]:
        body = f"<p class='empty'>{NO_SPRINT if shape is None else EMPTY}</p>"
        edges: list[list[str]] = []
    else:
        lines = mermaid_lines(shape, node_links(repo, open_prs(nodes), sessions))
        body = f"<pre class='mermaid'>{html.escape(chr(10).join(lines))}</pre>"
        edges = [[a, b] for a, b in shape["edges"]]
    return TEMPLATE.format(
        title=html.escape(page_title(repo)),
        notes="".join(f"<p class='note'>{note}</p>" for note in notes),
        body=body,
        edges=json.dumps(edges),
        mermaid=MERMAID_URL,
    )


TEMPLATE = """<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --bg: #ffffff; --fg: #1f2328; --muted: #59636e; --edge: #d0d7de;
  --hot: #cf222e; --link: #0969da; --frame: #f6f8fa; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1; --edge: #3d444d;
  --hot: #ff7b72; --link: #4493f8; --frame: #151b23; }} }}
:root[data-theme="dark"] {{ --bg: #0d1117; --fg: #e6edf3; --muted: #9198a1;
  --edge: #3d444d; --hot: #ff7b72; --link: #4493f8; --frame: #151b23; }}
body {{ margin: 0; padding: 16px; background: var(--bg); color: var(--fg);
  font-family: system-ui, sans-serif; }}
h1 {{ font-size: 1.25rem; margin: 0 0 4px; }}
.note {{ color: var(--muted); margin: 0 0 4px; font-size: .9rem; }}
.frame {{ margin-top: 12px; overflow-x: auto; background: var(--frame);
  border: 1px solid var(--edge); border-radius: 8px; padding: 8px; }}
.mermaid {{ direction: ltr; margin: 0; min-width: max-content; }}
.lnk {{ color: var(--link); display: inline-block; padding: 4px 2px; }}
.hot path, path.hot {{ stroke: var(--hot) !important; stroke-width: 3px !important; }}
</style>
</head>
<body>
<h1>{title}</h1>
{notes}
<div class="frame">{body}</div>
<script src="{mermaid}"></script>
<script>
const EDGES = {edges};
const dark = matchMedia("(prefers-color-scheme: dark)").matches;
function nodeId(ref) {{
  return "n" + ref.replace(/^#/, "").replace(/[^A-Za-z0-9]/g, "_");
}}
function edgePaths(a, b) {{
  return document.querySelectorAll(
    `[id^="L_${{a}}_${{b}}_"], [id^="L-${{a}}-${{b}}-"]`);
}}
function highlight(id) {{
  document.querySelectorAll(".hot").forEach(e => e.classList.remove("hot"));
  if (!id) return;
  for (const [a, b] of EDGES.map(e => e.map(nodeId)))
    if (a === id || b === id) edgePaths(a, b).forEach(p => p.classList.add("hot"));
}}
if (window.mermaid) {{
  mermaid.initialize({{ startOnLoad: false, securityLevel: "loose",
    theme: dark ? "dark" : "default", flowchart: {{ htmlLabels: true }} }});
  mermaid.run().then(() => {{
    document.querySelectorAll("g.node").forEach(g => {{
      const id = (g.id.match(/(n[A-Za-z0-9_]+?)-\\d+$/) || [])[1];
      g.addEventListener("mouseenter", () => highlight(id));
      g.addEventListener("mouseleave", () => highlight(null));
      g.addEventListener("click", e => {{
        if (!e.target.closest("a")) highlight(id);
      }});
    }});
  }});
}}
document.addEventListener("click", e => {{
  const a = e.target.closest("a.lnk");
  if (!a) return;
  e.preventDefault();
  window.open(a.href, "_blank", "noopener");
}});
</script>
</body>
</html>
"""
