"""Reads one spec file: its parts and the status line of each (#226, #242).

A part is a ## to #### heading that starts with a fixed id, S-<n>.<m>. Its first
non-empty line may be a status line:
- **מצב:** Done (#N): the part was delivered by issue N;
- **מצב:** פתוח (#N) or פתוח (#N, #M): open, and these issues build it;
- **מצב:** מחוץ להיקף: still read, but out of the format (spec_check.py warns on it).

spec_check.py checks the files and imports these names from here, so its callers
(sprint_state.py, the tests) keep importing them from spec_check.
"""

import re
from typing import NamedTuple

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
PART_LEVELS = (2, 3, 4)
PART_ID = re.compile(r"^S-(\d+)\.(\d+)(?:\s+(?:[·:–-]\s*)?(.*))?$")
STATUS_LINE = re.compile(r"^\*\*(?:מצב|status):\*\*\s*(.*?)\s*$", re.IGNORECASE)
STATUS_LIKE = re.compile(r"^\*\*\s*(?:מצב|status)\b", re.IGNORECASE)
STATUS_FORMS = "**מצב:** Done (#<N>) or **מצב:** פתוח (#<N>)"
DONE = re.compile(r"^done\s*\(#(\d+)\)$", re.IGNORECASE)
OPEN = re.compile(r"^(?:פתוח|open)\s*\((#\d+(?:\s*,\s*#\d+)*)\)$", re.IGNORECASE)
OUT_OF_SCOPE = ("מחוץ להיקף", "out of scope")


class Part(NamedTuple):
    """One part of a spec: id, name, heading line, status (done/open/out/None).

    `done_issue` is the issue of a Done line, `open_issues` those of an open line.
    """

    id: str
    name: str
    line: int
    status: str | None = None
    done_issue: int | None = None
    open_issues: tuple[int, ...] = ()


def lines_outside_fences(text: str) -> list[tuple[int, str]]:
    """(line number, line) for every line outside a ``` block: an example is no part."""
    found = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            found.append((number, line))
    return found


def read_status(value: str) -> tuple[str, int | None, tuple[int, ...]] | None:
    """(status, done issue, open issues) from a status line's value; None: unknown."""
    done = DONE.match(value)
    if done:
        return "done", int(done.group(1)), ()
    opened = OPEN.match(value)
    if opened:
        numbers = re.findall(r"#(\d+)", opened.group(1))
        return "open", None, tuple(int(number) for number in numbers)
    if value.lower() in OUT_OF_SCOPE:
        return "out", None, ()
    return None


def heading_part(level: int, text: str, number: int) -> Part | str | None:
    """The part a heading opens, an error message for a broken S- heading, or None."""
    if not text.startswith("S-"):
        return None
    match = PART_ID.match(text)
    if not match:
        return f"broken part heading {text!r}: write S-<n>.<m> · <name>"
    if level not in PART_LEVELS:
        return f"part {text.split()[0]} is at level {level}: parts are ## to ####"
    return Part(f"S-{match[1]}.{match[2]}", (match[3] or "").strip(), number)


def status_of(part: Part, line: str) -> Part | str:
    """The part with the status of its first line, or an error for a broken status line.

    A line that starts like a status line ("**מצב", "**status") but is not a known
    one is an error, so that "**מצב**: Done" never leaves a part open in silence.
    """
    status = STATUS_LINE.match(line)
    if status:
        value = read_status(status.group(1))
        if value:
            return part._replace(
                status=value[0], done_issue=value[1], open_issues=value[2]
            )
    elif not STATUS_LIKE.match(line):
        return part
    return f"unknown status line {line!r} under {part.id}: write {STATUS_FORMS}"


def parse_spec(text: str) -> tuple[list[Part], list[tuple[int, str]]]:
    """The parts of one spec file, and its errors as (line, message)."""
    parts: list[Part] = []
    errors: list[tuple[int, str]] = []
    first_line: dict[str, int] = {}
    waiting: Part | None = None
    for number, line in lines_outside_fences(text):
        heading = HEADING.match(line)
        if heading or (waiting and line.strip()):
            if waiting:
                found = waiting if heading else status_of(waiting, line.strip())
                parts.append(waiting if isinstance(found, str) else found)
                if isinstance(found, str):
                    errors.append((number, found))
            waiting = None
        if not heading:
            continue
        found = heading_part(len(heading[1]), heading[2], number)
        if isinstance(found, str):
            errors.append((number, found))
        elif found and found.id in first_line:
            first = first_line[found.id]
            message = f"duplicate id {found.id} (first at line {first})"
            errors.append((number, f"{message}: give this part a new number"))
        elif found:
            first_line[found.id] = number
            waiting = found
    if waiting:
        parts.append(waiting)
    return parts, errors
