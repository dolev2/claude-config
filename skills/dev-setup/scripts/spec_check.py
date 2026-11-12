"""Checks the spec files in docs/specs/ and prints their status table (#226).

A repo has one spec, docs/specs/<repo>.md (the format is in docs/specs/README.md),
whose chapters are its topics. Each part is a ## to #### heading that starts with a
fixed id, S-<n>.<m>, and an issue points at its parts on the "אפיון:" line of its
context section. Reading a file is spec_parse.py's.

Two kinds of findings, by Dolev's answer on #226:
- an error in a file (a duplicate id, a broken S- heading, an unknown status line):
  exit 1, so CI fails;
- a warning, never the exit code: a gap between the issues and the specs (a line that
  points nowhere, an open issue without a line, an open part without an issue, an
  open line naming an issue that is not open or does not point back), and, from the
  files alone (#242), an open part without its line, a part marked out of scope, and
  more than one spec file in a repo not yet merged into one.

A stale table of contents is an error, and a missing one a warning, so that a repo
whose specs predate it keeps a green CI until `--toc` adds one (spec_toc.py). A block
in the older form, without each part's status, that still matches the headings is also
a warning (#279).
The status links need owner/name: from --repo, else from the origin of --root.

Usage:
    spec_check.py [--root DIR] [--repo owner/name] [--no-issues] [--table] [--ref REF]
    spec_check.py --toc [--root DIR] [--repo owner/name]
    spec_check.py --changes BASE HEAD [--root DIR] [--repo owner/name] [--no-issues]
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import gh_rest
import issue_body
import spec_changes
import spec_toc
from spec_parse import Part, parse_spec

SPECS_DIR = "docs/specs"
NOT_STARTED = {"status:explore", "status:backlog"}
EXAMPLE_LINE = "אפיון: docs/specs/<repo>.md S-<n>.<m>"
OPEN_FORM = "**מצב:** פתוח (#<N>)"


class Finding(NamedTuple):
    """An error or a warning; `path` and `line` are None when it is in no file."""

    path: str | None
    line: int | None
    message: str


def part_warnings(path: str, parts: list[Part]) -> list[Finding]:
    """What a file's parts lack in themselves: an open part's line, a deleted part.

    Read from the file alone, so they warn with --no-issues too (#242).
    """
    found = []
    for part in parts:
        if part.status is None:
            message = f"{part.id} is open with no status line: write {OPEN_FORM}"
        elif part.status == "out":
            message = (
                f"{part.id} is marked out of scope: delete the part "
                "(its number never returns)"
            )
        else:
            continue
        found.append(Finding(path, part.line, message))
    return found


def files_warning(count: int) -> list[Finding]:
    """One warning when docs/specs/ holds more than one spec: one spec per repo."""
    if count <= 1:
        return []
    message = (
        f"{count} spec files in {SPECS_DIR}/: one spec per repo, "
        f"{SPECS_DIR}/<repo>.md (dev-setup step 8 merges them)"
    )
    return [Finding(None, None, message)]


def is_spec(name: str) -> bool:
    """A spec file's name: any .md in docs/specs/ but README.md."""
    return name.endswith(".md") and name.lower() != "readme.md"


def spec_files(root: Path) -> dict[str, str]:
    """{repo-relative path: text} of every spec file; README.md is no spec."""
    folder = root / SPECS_DIR
    if not folder.is_dir():
        return {}
    return {
        f"{SPECS_DIR}/{path.name}": path.read_text(encoding="utf-8")
        for path in sorted(folder.glob("*.md"))
        if is_spec(path.name)
    }


def git(root: Path, *args: str) -> str:
    """The stdout of a git command in `root`; a failure raises ValueError."""
    done = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, encoding="utf-8"
    )
    if done.returncode != 0:
        raise ValueError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def spec_files_at(root: Path, ref: str) -> dict[str, str]:
    """spec_files(root), but read from the git `ref` and not from the disk.

    The orchestrator's clone goes stale during a sprint while specs merge on GitHub,
    so it reads origin/<default> (#227). A ref without docs/specs/ gives {}; a ref
    git does not know is a ValueError.
    """
    # -z: without it git quotes a non-ASCII name, and `git show` cannot find it.
    listed = git(root, "ls-tree", "-z", "--name-only", ref, f"{SPECS_DIR}/")
    names = [name for name in listed.split("\0") if name]
    return {
        path: git(root, "show", f"{ref}:{path}")
        for path in sorted(names)
        if is_spec(path.rsplit("/", 1)[-1])
    }


def issue_spec(issue: dict) -> tuple[str, list[str]] | None:
    """The spec line of an issue: its context section's, else its Plan's.

    A bug has no context section (the bug form has none), so its short Plan's
    "- **אפיון:**" line names the part it breaks (#227).
    """
    parts = issue_body.sections(issue["body"])
    context = issue_body.section(parts, issue_body.CONTEXT_HEADINGS)
    found = issue_body.spec_line(context)
    return found or issue_body.spec_line(parts.get("plan", ""))


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


def open_line_gaps(
    path: str, part: Part, open_numbers: set[int], pointing: list[dict]
) -> list[Finding]:
    """What an open line names in vain: an issue not open, or one that points elsewhere.

    `pointing` are the open issues whose spec line names this part (#242).
    """
    pointing_numbers = {issue["number"] for issue in pointing}
    found = []
    for number in part.open_issues:
        if number not in open_numbers:
            message = f"{part.id} names #{number} in its status line: not an open issue"
        elif number not in pointing_numbers:
            message = (
                f"{part.id} names #{number} in its status line, but the spec line "
                f"of #{number} does not name {path} {part.id}"
            )
        else:
            continue
        found.append(Finding(path, part.line, message))
    return found


def gaps(specs: dict[str, list[Part]], issues: list[dict]) -> list[Finding]:
    """Every gap between the open issues and the specs. Gaps warn; they never fail."""
    found = [gap for issue in issues for gap in issue_gaps(specs, issue)]
    pointed = pointers(issues)
    open_numbers = {issue["number"] for issue in issues}
    for path, parts in specs.items():
        for part in parts:
            if part.status not in (None, "open"):
                continue
            pointing = pointed.get((path, part.id), [])
            # An open line already names its issues; open_line_gaps says which fail.
            if not pointing and not part.open_issues:
                message = f"{part.id} is open, and no open issue points at it"
                found.append(Finding(path, part.line, message))
            found += open_line_gaps(path, part, open_numbers, pointing)
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
        where = f" file={finding.path}" if finding.path else ""
        where += f",line={finding.line}" if finding.path and finding.line else ""
        print(f"::{kind}{where}::{annotation(finding.message)}")
    else:
        line = f":{finding.line}" if finding.line else ""
        place = f"{finding.path}{line}: " if finding.path else ""
        print(f"{kind}: {place}{finding.message}")


def summary(specs: dict[str, list[Part]], errors: int, warnings: int) -> str:
    """The last line: what was checked, and how many errors and warnings."""
    if not specs:
        return f"no spec files in {SPECS_DIR}/ yet; {warnings} warnings"
    parts = sum(len(found) for found in specs.values())
    return (
        f"{len(specs)} spec files, {parts} parts: {errors} errors, {warnings} warnings"
    )


def repo_name(root: Path, given: str | None) -> str:
    """owner/name for the issue links: `given`, else the origin of `root`; exits."""
    if given:
        return given
    try:
        url = git(root, "remote", "get-url", "origin")
    except ValueError:
        url = ""
    repo = gh_rest.repo_from_url(url)
    if not repo:
        sys.exit(gh_rest.NOT_A_REPO)
    return repo


def toc_findings(
    path: str, text: str, repo: str
) -> tuple[list[Finding], list[Finding]]:
    """(errors, warnings) of a file's table of contents.

    Stale fails; missing, or the older form without the status, only warns.
    """
    found = spec_toc.check(text, repo)
    if found is None:
        return [], []
    line, message = found
    if line == 0:
        return [], [Finding(path, None, message)]
    return [Finding(path, line, message)], []


def read_specs(
    root: Path, ref: str | None, repo: str | None = None
) -> tuple[dict[str, list[Part]], list[Finding], list[Finding]]:
    """The parsed spec files, from the disk or from `ref`, their errors and warnings.

    `ref` serves a clone that may be behind GitHub, like dev-ship's main folder (#227).
    `repo` is --repo; only a repo that has spec files needs one (`repo_name`).
    """
    try:
        files = spec_files_at(root, ref) if ref else spec_files(root)
    except ValueError as err:
        sys.exit(f"spec files not read: {err}")
    specs: dict[str, list[Part]] = {}
    errors: list[Finding] = []
    warnings: list[Finding] = []
    warnings += files_warning(len(files))
    if files:
        repo = repo_name(root, repo)
    for path, text in files.items():
        specs[path], found = parse_spec(text)
        errors += [Finding(path, line, message) for line, message in found]
        warnings += part_warnings(path, specs[path])
        toc_errors, toc_warnings = toc_findings(path, text, repo)
        errors += toc_errors
        warnings += toc_warnings
    return specs, errors, warnings


def write_tocs(root: Path, repo: str | None) -> int:
    """Rebuild the table of contents of each spec file on disk; print what changed."""
    files = spec_files(root)
    if files:
        repo = repo_name(root, repo)
    for path, text in files.items():
        new = spec_toc.write(text, repo)
        if new != text:
            (root / path).write_text(new, encoding="utf-8")
            print(f"table of contents written: {path}")
    return 0


def print_changes(args: argparse.Namespace) -> int:
    """`--changes`: the parts that differ between two refs, with their open issues.

    1 when the issues were not read (#244): without them there is nothing to offer.
    """
    root = Path(args.root)
    base, head = args.changes
    try:
        changes = spec_changes.compare(
            spec_files_at(root, base), spec_files_at(root, head)
        )
    except ValueError as err:
        sys.exit(f"spec files not read: {err}")
    pointed = None
    code = 0
    if not args.no_issues:
        try:
            pointed = pointers(fetch_issues(args.repo))
        except SystemExit as stop:
            emit("warning", Finding(None, None, f"issues not read: {stop.code}"))
            code = 1
    print("\n".join(spec_changes.report(changes, pointed)))
    return code


def main(argv: list[str] | None = None) -> int:
    """Check the specs; 1 if a file has an error, else 0 (gaps only warn)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="the repo root (default: .)")
    parser.add_argument("--repo", help="owner/name (default: the origin remote)")
    parser.add_argument("--no-issues", action="store_true", help="files only, no gh")
    parser.add_argument("--table", action="store_true", help="print the status table")
    parser.add_argument(
        "--ref",
        help="read the specs from this git ref (e.g. origin/main), not the disk",
    )
    parser.add_argument(
        "--toc", action="store_true", help="write the table of contents of each file"
    )
    parser.add_argument(
        "--changes",
        nargs=2,
        metavar=("BASE", "HEAD"),
        help="list the parts new, changed or deleted between two refs",
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.toc:
        return write_tocs(Path(args.root), args.repo)
    if args.changes:
        return print_changes(args)
    specs, errors, warnings = read_specs(Path(args.root), args.ref, args.repo)

    issues = None
    if not args.no_issues:
        try:
            issues = fetch_issues(args.repo)
        except SystemExit as stop:
            # gh_rest exits on a gh failure. Not reading the issues is no error in a
            # file, so it may not fail CI either (Dolev's answer on #226).
            warnings.append(Finding(None, None, f"issues not read: {stop.code}"))
        else:
            warnings += gaps(specs, issues)

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
