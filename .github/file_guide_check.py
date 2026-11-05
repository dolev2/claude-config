"""Fails when the file guide in README.md misses a file, or names one gone or twice.

From the dev-setup template (dolev2/claude-config#89). Each repo keeps a copy at
.github/file_guide_check.py and runs it in CI and before every PR:

    python .github/file_guide_check.py

Above the "# --- local ---" line the copy is identical to the template (lint_check.py
compares that part); below it, the files this repo's guide covers by a sentence.

How the guide is read, so that prose never counts as a row:
- only table rows inside the "מדריך קבצים" / "File guide" section;
- a heading with a folder in backticks ("### `skills/dev-setup/`: ...") is the prefix of
  the rows under it;
- first column: paths relative to that prefix. In a cell with several names, a name
  without "/" sits in the folder of the name before it. A name with "*" is a pattern;
- a row whose first column is a folder names its files in the other columns, by name or
  by name without extension (`AppShell` for AppShell.jsx). The folder alone covers
  nothing, so a new file in it still needs to be named.
"""

import re
import subprocess
import sys
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

GUIDE_HEADINGS = ("מדריך קבצים", "file guide")
HEADING = re.compile(r"^(#+)\s+(.*)$")
CODE = re.compile(r"`([^`]+)`")


def outside_fences(text: str) -> list[str]:
    """The text's lines, without code blocks: a "# comment" in one is no heading."""
    lines = []
    in_fence = False
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            lines.append(line)
    return lines


def guide_lines(readme: str) -> list[str] | None:
    """The guide section's lines, up to the next heading of its level, or None."""
    lines = outside_fences(readme)
    for index, line in enumerate(lines):
        heading = HEADING.match(line)
        if heading and any(h in heading[2].lower() for h in GUIDE_HEADINGS):
            level = len(heading[1])
            section = []
            for rest in lines[index + 1 :]:
                inner = HEADING.match(rest)
                if inner and len(inner[1]) <= level:
                    break
                section.append(rest)
            return section
    return None


def first_cell_paths(cell: str, prefix: str) -> list[str]:
    """The repo paths a first cell names; a bare name sits in the folder before it."""
    paths = []
    folder = prefix
    for name in CODE.findall(cell):
        path = (prefix if "/" in name else folder) + name
        paths.append(path)
        folder = path if path.endswith("/") else f"{PurePosixPath(path).parent}/"
        folder = "" if folder == "./" else folder
    return paths


def guide_rows(lines: list[str]) -> list[tuple[list[str], list[str]]]:
    """Each table row as (paths in its first column, names in its other columns)."""
    rows = []
    prefix = ""
    for line in lines:
        heading = HEADING.match(line)
        if heading:
            folders = [n for n in CODE.findall(heading[2]) if n.endswith("/")]
            prefix = folders[0] if folders else ""
        elif line.lstrip().startswith("|"):
            cells = line.strip().strip("|").split("|")
            names = [n for cell in cells[1:] for n in CODE.findall(cell)]
            rows.append((first_cell_paths(cells[0], prefix), names))
    return rows


def is_folder(path: str, files: list[str]) -> bool:
    """True when some file sits under the path."""
    folder = path.rstrip("/") + "/"
    return any(file.startswith(folder) for file in files)


def covers(path: str, names: list[str], file: str, files: list[str]) -> bool:
    """True when a first-column path, or a folder row's names, cover the file."""
    if file == path or ("*" in path and fnmatchcase(file, path)):
        return True
    folder = path.rstrip("/") + "/"
    if not is_folder(path, files) or not file.startswith(folder):
        return False
    inner = file[len(folder) :]
    if "/" in inner:
        return inner in names
    return bool({inner, PurePosixPath(inner).stem} & set(names))


def exists(path: str, files: list[str]) -> bool:
    """True for a file, a folder with files in it, or a pattern that matches one."""
    if "*" in path:
        return any(fnmatchcase(file, path) for file in files)
    return path in files or is_folder(path, files)


def check(
    readme: str, files: list[str], covered_by_pattern: list[str]
) -> tuple[list[str], list[str]] | None:
    """(files the guide misses, first-column paths that do not exist), or None."""
    lines = guide_lines(readme)
    if lines is None:
        return None
    rows = guide_rows(lines)
    missing = [
        file
        for file in files
        if not any(fnmatchcase(file, pattern) for pattern in covered_by_pattern)
        and not any(
            covers(path, names, file, files) for paths, names in rows for path in paths
        )
    ]
    gone = [path for paths, _ in rows for path in paths if not exists(path, files)]
    return missing, gone


def listed_twice(readme: str) -> list[str]:
    """First-column paths that more than one row names, in order of their first row."""
    # README.md merges with merge=union: when two branches edit the same row, both
    # versions stay, and this is what catches it.
    seen: set[str] = set()
    twice: list[str] = []
    for paths, _ in guide_rows(guide_lines(readme) or []):
        for path in paths:
            if path in seen and path not in twice:
                twice.append(path)
            seen.add(path)
    return twice


def repo_files(root: Path) -> list[str]:
    """Every file git tracks or would track (new files too), relative to the root."""
    # -z: without it git quotes a non-ASCII path ("\327\247..."), which then misses.
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    paths = [path for path in listed.stdout.split("\0") if path]
    return [path for path in paths if (root / path).is_file()]


def main(covered_by_pattern: list[str]) -> int:
    """Print what the guide misses and what it names in vain; 1 if anything, else 0."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # encoding: without it Windows decodes a non-ASCII path with the locale codepage.
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    root = Path(top.stdout.strip())
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8") if readme.exists() else ""
    result = check(text, repo_files(root), covered_by_pattern)
    if result is None:
        print('README.md has no "מדריך קבצים" / "File guide" section.')
        return 1
    missing, gone = result
    for file in missing:
        print(f"not in the guide: {file}")
    for path in gone:
        print(f"in the guide, but no such file: {path}")
    twice = listed_twice(text)
    for path in twice:
        print(f"in the guide twice: {path}")
    if missing or gone or twice:
        print("Add a row to the file guide in README.md, or remove the stale one.")
        return 1
    print("file guide complete")
    return 0


# --- local ---
# Files the guide covers by a sentence, not by name: tests, generated files, images.
COVERED_BY_PATTERN = [
    "hooks/test_*.py",
    "skills/*/SKILL.md",
]

if __name__ == "__main__":
    sys.exit(main(COVERED_BY_PATTERN))
