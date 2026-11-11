"""The table of contents of a spec file: built from its headings, kept in sync (#230).

A spec file holds its table of contents between two markers, right after the opening
lines. The block is never written by hand: `spec_check.py --toc` writes it from the
headings, and `spec_check.py` fails when it no longer matches them, so a part that is
added or renamed always reaches the table of contents in the same PR.
"""

import re

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


def build(text: str) -> list[str]:
    """The block between the markers, markers included, for the headings of `text`."""
    entries = [
        f"{'  ' * (level - 2)}- [{label(name)}](#{slug})"
        for level, name, slug in anchored(text)
    ]
    return [START, TITLE, "", *entries, END]


def check(text: str) -> tuple[int, str] | None:
    """(line, message) when the table of contents is missing or stale, else None."""
    lines = text.splitlines()
    found = region(lines)
    if found is None:
        return 0, f"no table of contents: run spec_check.py --toc to add {START}"
    start, end = found
    if lines[start : end + 1] != build(text):
        return start + 1, "the table of contents is stale: run spec_check.py --toc"
    return None


def write(text: str) -> str:
    """`text` with its table of contents rebuilt; a file with none gets one.

    A new block goes before the first ## heading, after the opening lines.
    """
    lines = text.splitlines()
    if region(lines) is None:
        first = next((i for i, line in enumerate(lines) if HEADING.match(line)), None)
        at = len(lines) if first is None else first
        lines[at:at] = [START, END, ""]
    start, end = region(lines)
    block = build("\n".join(lines))
    return "\n".join([*lines[:start], *block, *lines[end + 1 :]]) + "\n"
