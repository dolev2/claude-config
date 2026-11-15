"""Warns on a code, skill or pipeline file that a PR moved past its line limit.

Code and skills: about 300 lines, with the split questions (S-4.14). A pipeline doc
(skills/dev-setup/reference/*.md): about 150, with the questions of S-1.55 (place,
redundant, responsibility). The size is only a warning light: a file splits for a
reason, never for a number (rules/code-general.md, "מודולריות"). So the warning shows
the questions, not only the count, and it never fails the run. It goes only to a file
the PR moved past its limit: one that was already over it would warn on every PR
that touches it, and a warning that always shows is noise. Run in CI on every PR:

    python size_check.py --base origin/main

The decision: docs/decisions/369-split-by-reason.md.
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".ps1", ".sh"}
TEST_PATTERNS = ("test_*.py", "*_test.py", "*.test.*", "*.spec.*")
REFERENCE_DIR = PurePosixPath("skills/dev-setup/reference")
# The spec is one file on purpose (docs/specs/README.md): it never gets the warning.
SKIPPED_PREFIXES = ("docs/specs/",)

SPLIT_QUESTIONS = (
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

PIPELINE_QUESTIONS = (
    "השאלות של מסמך צינור (S-1.55):",
    "1. מקום: מה בקובץ גנרי, ושייך לקובץ בעלים אחר (reference/owners.md).",
    "2. מיותר: מה חוזר על מה שכתוב במקום אחר, או לא נחוץ בכלל.",
    "3. אחריות: האם הקובץ מחזיק יותר מנושא אחד, ואז שאלות הפיצול (S-4.14).",
    "הכל במקום: המסמך נשאר, והתשובה נכתבת בשורה במסירה של ה-PR.",
)


@dataclass(frozen=True)
class Rule:
    """The limit of a kind of file, and the questions its warning shows."""

    limit: int
    questions: tuple[str, ...]


CODE_RULE = Rule(300, SPLIT_QUESTIONS)
PIPELINE_RULE = Rule(150, PIPELINE_QUESTIONS)


def rule_for(path: str) -> Rule | None:
    """The rule that covers this file, or None: tests and the spec are never checked."""
    pure = PurePosixPath(path)
    if pure.parent == REFERENCE_DIR and pure.suffix == ".md":
        return PIPELINE_RULE
    if REFERENCE_DIR in pure.parents:
        return None
    if path.startswith(SKIPPED_PREFIXES) or "tests" in pure.parts[:-1]:
        return None
    if any(fnmatchcase(pure.name, p) for p in TEST_PATTERNS):
        return None
    if pure.suffix in CODE_SUFFIXES:
        return CODE_RULE
    if pure.suffix == ".md" and path.startswith("skills/"):
        return CODE_RULE
    return None


def crossed(before: int | None, after: int | None, limit: int) -> bool:
    """Whether the PR moved the file past the limit; None is a missing file."""
    return after is not None and after > limit and (before is None or before <= limit)


def git(*args: str) -> subprocess.CompletedProcess:
    """Runs git and returns the result, without raising on a non-zero exit."""
    return subprocess.run(["git", *args], capture_output=True, text=True)


def line_count(ref: str, path: str) -> int | None:
    """The lines of a file at a ref, or None when the file is not there."""
    shown = git("show", f"{ref}:{path}")
    return len(shown.stdout.splitlines()) if shown.returncode == 0 else None


def changed_paths(name_status: str) -> list[tuple[str, str]]:
    """(path in base, path at HEAD) from `git diff --name-status -M -z`.

    A renamed file is counted at its old path in base, so a move of a long file is not
    read as a new one.
    """
    fields = name_status.split("\0")
    pairs, i = [], 0
    while i < len(fields) - 1:
        status = fields[i]
        if status[:1] in ("R", "C"):
            pairs.append((fields[i + 1], fields[i + 2]))
            i += 3
        else:
            pairs.append((fields[i + 1], fields[i + 1]))
            i += 2
    return pairs


Finding = tuple[str, int | None, int, Rule]


def findings(base: str, pairs: list[tuple[str, str]]) -> list[Finding]:
    """(path, lines in base, lines at HEAD, rule) for each checked file that crossed."""
    found = []
    for old, path in pairs:
        rule = rule_for(path)
        if rule is None:
            continue
        before, after = line_count(base, old), line_count("HEAD", path)
        if crossed(before, after, rule.limit):
            found.append((path, before, after, rule))
    return found


def warning(path: str, before: int | None, after: int, rule: Rule) -> str:
    """One GitHub annotation; %0A is a line break inside it."""
    was = "קובץ חדש" if before is None else f"{before} שורות"
    head = (
        f"עבר את הסף של כ-{rule.limit} שורות ({was} ← {after})."
        " זו נורת אזהרה, לא חובה לשנות את הקובץ."
    )
    escaped = path.replace("%", "%25").replace(":", "%3A").replace(",", "%2C")
    return f"::warning file={escaped}::" + "%0A".join((head, *rule.questions))


def summary(found: list[Finding]) -> str:
    """The job summary: a heading per limit, its files, then its questions once."""
    out = []
    for rule in sorted({f[3] for f in found}, key=lambda r: -r.limit):
        rows = [
            f"- הקובץ `{p}`: {'חדש' if b is None else b} ← {a} שורות"
            for p, b, a, r in found
            if r == rule
        ]
        heading = f"### קבצים שעברו את הסף של כ-{rule.limit} שורות"
        out += [heading, *rows, "", *rule.questions, ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args(argv)
    diff = git("diff", "--name-status", "-M", "-z", f"{args.base}...HEAD")
    if diff.returncode != 0:
        print(f"אי אפשר להשוות ל-{args.base}: {diff.stderr.strip()}", file=sys.stderr)
        return 2
    found = findings(args.base, changed_paths(diff.stdout))
    if not found:
        print("אף קובץ לא עבר את סף השורות שלו ב-PR הזה.")
        return 0
    for finding in found:
        print(warning(*finding))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as out:
            out.write(summary(found))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
