"""The table of contents of a spec file: built from its headings, kept in sync (#230).

A spec file holds its table of contents between two markers, right after the opening
lines. The block is never written by hand: `spec_check.py --toc` writes it from the
headings, and `spec_check.py` fails when it no longer matches them, so a part that is
added or renamed always reaches the table of contents in the same PR.

Each part's entry also shows its status line, with links to its issues (S-1.39, #279):
` · גמור: [#226](...)` or ` · פתוח: [#280](...), [#281](...)`. A part with no status
line, or out of scope, gets nothing. The links are full URLs: GitHub does not link a
bare #N inside a .md file, and a relative link breaks on a branch whose name has a "/".
"""

import re

from spec_parse import parse_spec

START = "<!-- toc -->"
END = "<!-- /toc -->"
TITLE = "## תוכן העניינים"
HEADING = re.compile(r"^(#{2,4})\s+(.*?)\s*$")
PART = re.compile(r"^(S-\d+\.\d+)\s+(?:[·:–-]\s*)?(.*)$")
# GitHub keeps letters, digits, "_", "-" and spaces of a heading's text in its anchor.
NOT_IN_ANCHOR = re.compile(r"[^\w\- ]")


def anchor(text: str, seen: dict[str, int]) -> str:
    """The anchor GitHub gives a heading; a repeated one gets -1, -2 as on GitHub."""
    base = NOT_IN_ANCHOR.sub("", text.replace("`", "").lower()).replace(" ", "-")
    count = seen.get(base, 0)
    seen[base] = count + 1
    return base if count == 0 else f"{base}-{count}"


def label(text: str) -> str:
    """The text of an entry: a part puts its name first and its id after it.

    An entry that starts with "S-" would turn the whole list left to right, since
    the screen sets a block's direction by its first strong letter.
    """
    part = PART.match(text)
    return f"{part[2]} ({part[1]})" if part and part[2] else text


def region(lines: list[str]) -> tuple[int, int] | None:
    """(start, end) line indexes of the markers, or None when the file has none."""
    starts = [i for i, line in enumerate(lines) if line.strip() == START]
    ends = [i for i, line in enumerate(lines) if line.strip() == END]
    if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
        return None
    return starts[0], ends[0]


def headings(lines: list[str]) -> list[tuple[int, str]]:
    """(level, text) of every ## to #### heading outside code blocks and the markers."""
    found = []
    in_fence = in_toc = False
    for line in lines:
        stripped = line.strip()
        if stripped in (START, END):
            in_toc = stripped == START
        elif stripped.startswith("```"):
            in_fence = not in_fence
        elif not (in_fence or in_toc):
            match = HEADING.match(line)
            if match:
                found.append((len(match[1]), match[2]))
    return found


def anchored(text: str) -> list[tuple[int, str, str]]:
    """(level, text, anchor) of every heading, counted as GitHub counts the repeats.

    The title of the table of contents comes first on the page, so it is counted first.
    """
    seen: dict[str, int] = {}
    anchor(TITLE.removeprefix("## "), seen)
    return [
        (level, name, anchor(name, seen)) for level, name in headings(text.splitlines())
    ]


def part_anchors(text: str) -> dict[str, str]:
    """{part id: the anchor of its heading}, to link to a part from /status (S-1.41)."""
    return {
        part[1]: slug for _, name, slug in anchored(text) if (part := PART.match(name))
    }


def issue_links(repo: str, numbers: tuple[int, ...]) -> str:
    """Links to the issues of `repo`, comma separated: [#N](https://github.com/...)."""
    return ", ".join(
        f"[#{number}](https://github.com/{repo}/issues/{number})" for number in numbers
    )


def statuses(text: str, repo: str) -> dict[str, str]:
    """{part id: the status the entry ends with}, for the done and open parts only."""
    found = {}
    for part in parse_spec(text)[0]:
        if part.status == "done":
            found[part.id] = f" · גמור: {issue_links(repo, (part.done_issue,))}"
        elif part.status == "open":
            found[part.id] = f" · פתוח: {issue_links(repo, part.open_issues)}"
    return found


def build(text: str, repo: str | None = None) -> list[str]:
    """The block between the markers, markers included, for the headings of `text`.

    `repo` (owner/name) adds each part's status and issues; None builds the older form
    without them, which `check` still accepts with a warning.
    """
    status = statuses(text, repo) if repo else {}
    entries = []
    for level, name, slug in anchored(text):
        part = PART.match(name)
        tail = status.get(part[1], "") if part else ""
        entries.append(f"{'  ' * (level - 2)}- [{label(name)}](#{slug}){tail}")
    return [START, TITLE, "", *entries, END]


def check(text: str, repo: str) -> tuple[int, str] | None:
    """(line, message) when the table of contents is missing, old or stale, else None.

    Line 0 is a warning: no block at all, or a block in the older form without the
    status that still matches the headings, so a repo whose spec predates it keeps a
    green CI until `--toc` runs there (#279).
    """
    lines = text.splitlines()
    found = region(lines)
    if found is None:
        return 0, f"no table of contents: run spec_check.py --toc to add {START}"
    start, end = found
    block = lines[start : end + 1]
    if block == build(text, repo):
        return None
    if block == build(text):
        return 0, "the table of contents has no status: run spec_check.py --toc"
    return start + 1, "the table of contents is stale: run spec_check.py --toc"


def write(text: str, repo: str) -> str:
    """`text` with its table of contents rebuilt; a file with none gets one.

    A new block goes before the first ## heading, after the opening lines.
    """
    lines = text.splitlines()
    if region(lines) is None:
        first = next((i for i, line in enumerate(lines) if HEADING.match(line)), None)
        at = len(lines) if first is None else first
        lines[at:at] = [START, END, ""]
    start, end = region(lines)
    block = build("\n".join(lines), repo)
    return "\n".join([*lines[:start], *block, *lines[end + 1 :]]) + "\n"
