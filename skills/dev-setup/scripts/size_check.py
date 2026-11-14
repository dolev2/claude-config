"""Warns on a code or skill file that a PR moved past about 300 lines (S-4.14).

The size is only a warning light: a file splits for a reason, never for a number
(rules/code-general.md, "מודולריות"). So the warning shows the split questions, not only
the count, and it never fails the run. It goes only to a file the PR moved past
the limit: one that was already over it would warn on every PR that touches it, and a
warning that always shows is noise. Run in CI on every PR:

    python size_check.py --base origin/main

The decision: docs/decisions/369-split-by-reason.md.
"""

import argparse
import os
import subprocess
import sys
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

LIMIT = 300
CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".ps1", ".sh"}
TEST_PATTERNS = ("test_*.py", "*_test.py", "*.test.*", "*.spec.*")
# The pipeline docs have a limit of their own, 150 (S-1.55, claude-config #382), and the
# spec is one file on purpose: neither gets this warning.
SKIPPED_PREFIXES = ("docs/specs/", "skills/dev-setup/reference/")

QUESTIONS = (
    "מתי מפצלים:",
    "1. נושא אחר: לחלקים יש סיבות שונות להשתנות.",
    "2. גנרי מול ספציפי: חלק שלא יודע כלום על הנושא, וקובץ אחר צריך אותו.",
    "3. חזרה: אותו דפוס בשלושה מקומות.",
    "4. מי קורא ומתי: חלק שנחוץ רק בצעד אחד.",
    "מתי לא מפצלים:",
    "1. הקובץ הוא נושא אחד, והחלקים שלו קוראים זה לזה.",
    "2. הקובץ החדש היה צריך כמעט כל מה שבקובץ הישן.",
    "נושא אחד: הקובץ נשאר, ומדריך הקבצים אומר למה (rules/code-general.md).",
)


def is_checked(path: str) -> bool:
    """Whether the warning covers this file: code or a skill, not a test or the spec."""
    pure = PurePosixPath(path)
    if path.startswith(SKIPPED_PREFIXES) or "tests" in pure.parts[:-1]:
        return False
    if any(fnmatchcase(pure.name, p) for p in TEST_PATTERNS):
        return False
    if pure.suffix in CODE_SUFFIXES:
        return True
    return pure.suffix == ".md" and path.startswith("skills/")


def crossed(before: int | None, after: int | None) -> bool:
    """Whether the PR moved the file past the limit; None is a missing file."""
    return after is not None and after > LIMIT and (before is None or before <= LIMIT)


def git(*args: str) -> subprocess.CompletedProcess:
    """Runs git and returns the result, without raising on a non-zero exit."""
    return subprocess.run(["git", *args], capture_output=True, text=True)


def line_count(ref: str, path: str) -> int | None:
    """The lines of a file at a ref, or None when the file is not there."""
    shown = git("show", f"{ref}:{path}")
    return len(shown.stdout.splitlines()) if shown.returncode == 0 else None


def findings(base: str, files: list[str]) -> list[tuple[str, int | None, int]]:
    """(path, lines in base, lines at HEAD) for each checked file that crossed."""
    found = []
    for path in files:
        if not is_checked(path):
            continue
        before, after = line_count(base, path), line_count("HEAD", path)
        if crossed(before, after):
            found.append((path, before, after))
    return found


def warning(path: str, before: int | None, after: int) -> str:
    """One GitHub annotation; %0A is a line break inside it."""
    was = "קובץ חדש" if before is None else f"{before} שורות"
    head = (
        f"עבר את הסף של כ-{LIMIT} שורות ({was} ← {after}). זו נורת אזהרה, לא חובה לפצל."
    )
    return f"::warning file={path}::" + "%0A".join((head, *QUESTIONS))


def summary(found: list[tuple[str, int | None, int]]) -> str:
    """The job summary: every file, then the questions once."""
    rows = [f"- `{p}`: {'חדש' if b is None else b} ← {a} שורות" for p, b, a in found]
    return "\n".join(
        ["### קבצים שעברו את הסף של כ-300 שורות", *rows, "", *QUESTIONS, ""]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args(argv)
    diff = git("diff", "--name-only", f"{args.base}...HEAD")
    if diff.returncode != 0:
        print(f"אי אפשר להשוות ל-{args.base}: {diff.stderr.strip()}", file=sys.stderr)
        return 2
    found = findings(args.base, diff.stdout.split())
    if not found:
        print(f"אף קובץ לא עבר את הסף של כ-{LIMIT} שורות ב-PR הזה.")
        return 0
    for path, before, after in found:
        print(warning(path, before, after))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as out:
            out.write(summary(found))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
