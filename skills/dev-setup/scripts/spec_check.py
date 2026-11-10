"""Checks the spec files in docs/specs/ and prints their status table (#226).

A spec file (docs/specs/<topic>.md; the format is in docs/specs/README.md) splits a
topic into parts. Each part is a ## to #### heading that starts with a fixed id,
S-<n>.<m>, and an issue points at its parts on the "אפיון:" line of its context section.

Two kinds of findings, by Dolev's answer on #226:
- an error in a file (a duplicate id, a broken S- heading, an unknown status line):
  exit 1, so CI fails;
- a gap between the issues and the specs (a line that points nowhere, an open issue
  without a line, an open part without an issue): a warning only, never the exit code.

Usage:
    spec_check.py [--root DIR] [--repo owner/name] [--no-issues] [--table]
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple

import gh_rest
import issue_body

SPECS_DIR = "docs/specs"
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
PART_LEVELS = (2, 3, 4)
PART_ID = re.compile(r"^S-(\d+)\.(\d+)(?:\s+(?:[·:–-]\s*)?(.*))?$")
STATUS_LINE = re.compile(r"^\*\*(?:מצב|status):\*\*\s*(.*?)\s*$", re.IGNORECASE)
STATUS_LIKE = re.compile(r"^\*\*\s*(?:מצב|status)\b", re.IGNORECASE)
STATUS_FORMS = "**מצב:** Done (#<N>) or **מצב:** מחוץ להיקף"
DONE = re.compile(r"^done\s*\(#(\d+)\)$", re.IGNORECASE)
OUT_OF_SCOPE = ("מחוץ להיקף", "out of scope")
NOT_STARTED = {"status:explore", "status:backlog"}
EXAMPLE_LINE = "אפיון: docs/specs/<topic>.md S-<n>.<m>"


class Part(NamedTuple):
    """One part of a spec: its id, name, heading line, and status (done/out/None)."""

    id: str
    name: str
    line: int
    status: str | None = None
    done_issue: int | None = None


class Finding(NamedTuple):
    """An error or a warning; `path` and `line` are None when it is in no file."""

    path: str | None
    line: int | None
    message: str


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


def read_status(value: str) -> tuple[str, int | None] | None:
    """("done", N) or ("out", None) from a status line's value, or None if unknown."""
    done = DONE.match(value)
    if done:
        return "done", int(done.group(1))
    if value.lower() in OUT_OF_SCOPE:
        return "out", None
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
            return part._replace(status=value[0], done_issue=value[1])
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


def spec_files(root: Path) -> dict[str, str]:
    """{repo-relative path: text} of every spec file; README.md is no spec."""
    folder = root / SPECS_DIR
    if not folder.is_dir():
        return {}
    return {
        f"{SPECS_DIR}/{path.name}": path.read_text(encoding="utf-8")
        for path in sorted(folder.glob("*.md"))
        if path.name.lower() != "readme.md"
    }


def issue_spec(issue: dict) -> tuple[str, list[str]] | None:
    """The spec line of an issue's context section, as issue_body.spec_line reads it."""
    parts = issue_body.sections(issue["body"])
    context = issue_body.section(parts, issue_body.CONTEXT_HEADINGS)
    return issue_body.spec_line(context)


def pointers(issues: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """{(spec path, part id): the open issues whose spec line names that part}."""
    found: dict[tuple[str, str], list[dict]] = {}
    for issue in issues:
        line = issue_spec(issue)
        if line:
            path = line[0].removeprefix("./")
            for part_id in line[1]:
                found.setdefault((path, part_id), []).append(issue)
    return found


def issue_gaps(specs: dict[str, list[Part]], issue: dict) -> list[Finding]:
    """What one open issue's spec line lacks, or points at in vain."""
    number = issue["number"]
    line = issue_spec(issue)
    if line is None:
        if "status:backlog" in issue["labels"]:
            return []
        return [Finding(None, None, f"#{number} has no spec line ({EXAMPLE_LINE})")]
    path, ids = line[0].removeprefix("./"), line[1]
    if not path or not ids:
        missing = "file" if not path else "part id"
        return [Finding(None, None, f"#{number}: its spec line has no {missing}")]
    if path not in specs:
        return [Finding(None, None, f"#{number} points at {path}: no such spec file")]
    known = {part.id for part in specs[path]}
    return [
        Finding(None, None, f"#{number} points at {path} {part_id}: no such part")
        for part_id in ids
        if part_id not in known
    ]


def gaps(specs: dict[str, list[Part]], issues: list[dict]) -> list[Finding]:
    """Every gap between the open issues and the specs. Gaps warn; they never fail."""
    found = [gap for issue in issues for gap in issue_gaps(specs, issue)]
    pointed = pointers(issues)
    for path, parts in specs.items():
        found += [
            Finding(
                path, part.line, f"{part.id} is open, and no open issue points at it"
            )
            for part in parts
            if part.status is None and (path, part.id) not in pointed
        ]
    return found


def part_state(part: Part, issues: list[dict] | None) -> tuple[str, str]:
    """(state, issues) of a part for the table; `issues` None: they were not read."""
    if part.status == "done":
        return "Done", f"#{part.done_issue}"
    if part.status == "out":
        return "מחוץ להיקף", ""
    if issues is None:
        return "לא נבדק", ""
    if not issues:
        return "אין issue", ""
    started = any(not issue["labels"] & NOT_STARTED for issue in issues)
    numbers = ", ".join(f"#{issue['number']}" for issue in issues)
    return ("בעבודה" if started else "לא התחיל"), numbers


def table(specs: dict[str, list[Part]], issues: list[dict] | None) -> str:
    """A Markdown status table per spec file: id, name, state, issue."""
    pointed = pointers(issues or [])
    blocks = []
    for path, parts in specs.items():
        rows = [f"### {path}", "", "| מזהה | שם | מצב | issue |", "|---|---|---|---|"]
        for part in parts:
            found = None if issues is None else pointed.get((path, part.id), [])
            state, numbers = part_state(part, found)
            name = part.name.replace("|", "\\|")
            rows.append(f"| {part.id} | {name} | {state} | {numbers} |")
        blocks.append("\n".join(rows))
    return "\n\n".join(blocks)


def fetch_issues(repo: str | None) -> list[dict]:
    """The open issues of `repo` (pull requests left out): number, label names, body."""
    repo = repo or gh_rest.current_repo()
    items = gh_rest.api_list(f"repos/{repo}/issues?state=open&per_page=100")
    return [
        {
            "number": item["number"],
            "labels": {label["name"] for label in item["labels"]},
            "body": item.get("body") or "",
        }
        for item in items
        if "pull_request" not in item
    ]


def annotation(text: str) -> str:
    """`text` escaped for a workflow command: a line break would end the annotation."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def emit(kind: str, finding: Finding) -> None:
    """Print a finding; in GitHub Actions as an annotation, so it shows on the PR."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        where = f" file={finding.path},line={finding.line}" if finding.path else ""
        print(f"::{kind}{where}::{annotation(finding.message)}")
    else:
        place = f"{finding.path}:{finding.line}: " if finding.path else ""
        print(f"{kind}: {place}{finding.message}")


def summary(specs: dict[str, list[Part]], errors: int, warnings: int) -> str:
    """The last line: what was checked, and how many errors and warnings."""
    if not specs:
        return f"no spec files in {SPECS_DIR}/ yet; {warnings} warnings"
    parts = sum(len(found) for found in specs.values())
    return (
        f"{len(specs)} spec files, {parts} parts: {errors} errors, {warnings} warnings"
    )


def main(argv: list[str] | None = None) -> int:
    """Check the specs; 1 if a file has an error, else 0 (gaps only warn)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="the repo root (default: .)")
    parser.add_argument("--repo", help="owner/name (default: the origin remote)")
    parser.add_argument("--no-issues", action="store_true", help="files only, no gh")
    parser.add_argument("--table", action="store_true", help="print the status table")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    specs: dict[str, list[Part]] = {}
    errors: list[Finding] = []
    for path, text in spec_files(Path(args.root)).items():
        specs[path], found = parse_spec(text)
        errors += [Finding(path, line, message) for line, message in found]

    issues = None
    warnings: list[Finding] = []
    if not args.no_issues:
        try:
            issues = fetch_issues(args.repo)
        except SystemExit as stop:
            # gh_rest exits on a gh failure. Not reading the issues is no error in a
            # file, so it may not fail CI either (Dolev's answer on #226).
            warnings.append(Finding(None, None, f"issues not read: {stop.code}"))
        else:
            warnings = gaps(specs, issues)

    for finding in errors:
        emit("error", finding)
    for finding in warnings:
        emit("warning", finding)
    if args.table and specs:
        print(table(specs, issues))
    print(summary(specs, len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
