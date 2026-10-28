"""Reads the sections of a pipeline issue body: the goal, the context, the Plan's files.

The headings are the ones of the task form (dolev2/.github, task.yml), at ## or ###, the
level the repo's issues use. Used by audit_sprint.py.
"""

import re

GOAL_HEADINGS = ("מה רוצים", "goal")
CONTEXT_HEADINGS = ("הקשר / קישורים", "context")
FILES_HEADING = re.compile(r"^#{4,6}\s+(קבצים שצפויים להשתנות|files)", re.IGNORECASE)
SECTION = re.compile(r"^#{2,3}\s+(.+?)\s*$")
SUBHEADING = re.compile(r"^#{4,6}\s")
DEPENDENCY_LINE = re.compile(r"^\s*(תלוי ב|depends on)\s*:(.*)$", re.IGNORECASE)
ISSUE_REF = re.compile(r"(?<![\w/])#(\d+)\b")
FIRST_CODE = re.compile(r"`([^`]+)`")


def sections(body: str) -> dict[str, str]:
    """Splits an issue body by its ## / ### headings; keys are lower-cased headings."""
    found: dict[str, list[str]] = {}
    current = ""
    for line in body.splitlines():
        match = SECTION.match(line)
        if match:
            current = match.group(1).lower()
            found[current] = []
        elif current:
            found[current].append(line)
    return {name: "\n".join(lines) for name, lines in found.items()}


def section(parts: dict[str, str], headings: tuple[str, ...]) -> str:
    return next((parts[h] for h in headings if h in parts), "")


def dependency_line(context: str) -> list[int] | None:
    """The issues on the "תלוי ב:" line, or None when the body has no such line."""
    for line in context.splitlines():
        match = DEPENDENCY_LINE.match(line)
        if match:
            return sorted({int(n) for n in ISSUE_REF.findall(match.group(2))})
    return None


def plan_files(plan: str) -> set[str]:
    """The first `path` of each bullet under the Plan's "files expected to change"."""
    files: set[str] = set()
    inside = False
    for line in plan.splitlines():
        if FILES_HEADING.match(line):
            inside = True
        elif SUBHEADING.match(line):
            inside = False
        elif inside and line.lstrip().startswith("- "):
            match = FIRST_CODE.search(line)
            if match:
                files.add(match.group(1))
    return files


def mentioned(text: str) -> set[int]:
    """The issue numbers named in `text`, outside its dependency line."""
    lines = (line for line in text.splitlines() if not DEPENDENCY_LINE.match(line))
    return {int(n) for n in ISSUE_REF.findall("\n".join(lines))}
