"""The "בריפו:" line of each spec chapter: the folders the chapter lives in (S-1.38).

The first non-empty line under a chapter heading (`## פרק <n> · <name>`) is
`**בריפו:** `hooks/`, `skills/dev-setup/reference/``: repo-relative folders, each in
backticks. From there the folder's README leads to the file, so a chapter that names a
folder that is gone sends its reader nowhere. In English: `**In repo:**`.

A broken line is an error, so a renamed folder cannot leave the spec behind. A chapter
without the line only warns, so a repo whose spec predates the line keeps a green CI
until the chapter is touched, like a missing table of contents (S-1.35).
"""

import re
from collections.abc import Callable
from typing import NamedTuple

from spec_parse import lines_outside_fences

CHAPTER = re.compile(r"^##\s+(?:פרק|chapter)\s+(\d+)\b", re.IGNORECASE)
REPO_LINE = re.compile(r"^\*\*(?:בריפו|in repo):\*\*(.*)$", re.IGNORECASE)
PATH = re.compile(r"`([^`]*)`")
FORM = "**בריפו:** `<folder>/`, `<folder>/`"

Finding = tuple[int, str]


class Chapter(NamedTuple):
    """A chapter heading, and the first non-empty line under it ("" when none)."""

    number: str
    line: int
    first: str = ""
    first_line: int = 0


def chapters(text: str) -> list[Chapter]:
    """Every chapter of a spec file, with its first line.

    Code blocks are skipped: a chapter heading inside an example is no chapter.
    """
    found: list[Chapter] = []
    waiting = False
    for number, line in lines_outside_fences(text):
        heading = CHAPTER.match(line)
        if heading:
            found.append(Chapter(heading[1], number))
            waiting = True
        elif waiting and line.strip():
            found[-1] = found[-1]._replace(first=line.strip(), first_line=number)
            waiting = False
    return found


def path_error(path: str, is_dir: Callable[[str], bool]) -> str | None:
    """Why one path on the line is wrong, or None when it is a folder of the repo."""
    clean = path.strip()
    if clean.startswith("/") or re.match(r"^[A-Za-z]:", clean):
        return f"`{path}` is an absolute path: write it relative to the repo root"
    if ".." in clean.split("/"):
        return f"`{path}` leaves the repo with '..': write it from the repo root"
    folder = clean.rstrip("/")
    if folder in ("", "."):
        return f"`{path}` is the repo root: name the chapter's own folders"
    if not is_dir(folder):
        return f"`{path}` is no folder in the repo (the line names folders only)"
    return None


def line_errors(
    at: int, chapter: str, value: str, is_dir: Callable[[str], bool]
) -> list[Finding]:
    """The errors of one chapter's repo line; `value` is the text after its label."""
    paths = [path for path in PATH.findall(value) if path.strip()]
    if not paths:
        message = f"chapter {chapter}: its repo line names no folder: write {FORM}"
        return [(at, message)]
    found = []
    for path in paths:
        error = path_error(path, is_dir)
        if error:
            message = f"chapter {chapter}: {error}; fix the line, or the folder's name"
            found.append((at, message))
    return found


def check(
    text: str, is_dir: Callable[[str], bool]
) -> tuple[list[Finding], list[Finding]]:
    """(errors, warnings) of the repo lines of a spec file, as (line, message).

    `is_dir` tells whether a repo-relative path is a folder: the disk, or a git ref.
    """
    errors: list[Finding] = []
    warnings: list[Finding] = []
    for chapter in chapters(text):
        line = REPO_LINE.match(chapter.first)
        if line is None:
            message = f"chapter {chapter.number} has no repo line: write {FORM} first"
            warnings.append((chapter.line, message))
            continue
        errors += line_errors(chapter.first_line, chapter.number, line[1], is_dir)
    return errors, warnings
