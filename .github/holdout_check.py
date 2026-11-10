"""Fails when one diff changes a skill and the held-out eval set together (#183).

The held-out cases in evals/holdout/ are never tuned on: a PR that changes a skill and
the held-out set at once could make the set fit the new text, and its score would read
better than real use. So a skill change (skills/*/SKILL.md, skills/dev-setup/reference/)
and a change in evals/holdout/ go in separate PRs. Run in CI on every PR:

    python .github/holdout_check.py --base origin/main

The decision: docs/decisions/183-skill-evals.md.
"""

import argparse
import subprocess
import sys
from fnmatch import fnmatchcase

HOLDOUT = "evals/holdout/"
SKILL_PATTERNS = ("skills/*/SKILL.md", "skills/dev-setup/reference/*")


def changed_files(base: str) -> list[str]:
    """Files changed between base and HEAD."""
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return out.split()


def holdout_exists(base: str) -> bool:
    """Whether base already has the held-out set; the PR that creates it is exempt."""
    out = subprocess.run(
        ["git", "ls-tree", "--name-only", base, HOLDOUT],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return bool(out.strip())


def conflict(files: list[str]) -> tuple[list[str], list[str]]:
    """The skill files and the held-out files of one diff; both non-empty fails."""
    skills = [f for f in files if any(fnmatchcase(f, p) for p in SKILL_PATTERNS)]
    holdout = [f for f in files if f.startswith(HOLDOUT)]
    return skills, holdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args(argv)
    if not holdout_exists(args.base):
        print("הסט השמור עוד לא קיים ב-base: אין מה לבדוק.")
        return 0
    skills, holdout = conflict(changed_files(args.base))
    if skills and holdout:
        print("שינוי בסקיל ובסט השמור באותו PR.")
        print("העבירו את השינוי ב-evals/holdout/ ל-PR נפרד.")
        print("הסקילים: " + ", ".join(skills))
        print("הסט השמור: " + ", ".join(holdout))
        return 1
    print("הסט השמור לא משתנה יחד עם סקיל.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
