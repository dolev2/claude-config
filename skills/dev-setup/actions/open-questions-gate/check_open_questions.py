"""Warn when an issue reaches review while it still has open questions.

Why this exists
---------------
`status:in-review` means "the PR is open; Dolev reviews it and asks for the merge".
That is the last stop before the merge, so a question still unanswered must be seen
there: once the issue is merged it moves to `status:done` and lands in Done, where
nobody re-reads the thread. claude-config #108 moved the gate here from `status:done`,
which now means "merged" and comes too late to stop anything. On `status:done` the gate
only clears: ticking the last box after the merge removes the warning label, but a merge
Dolev chose to make with a box open raises no new warning.

What counts as an open question
-------------------------------
The `## שאלות פתוחות` section of the issue body, read by the pipeline's one reader,
`skills/dev-setup/scripts/open_questions.py` (S-1.75), which holds the rules. The
action's checkout is the whole of claude-config, so that folder is always next to it.

Why it fails the run
--------------------
An issue comment alone is easy to miss in a busy notification inbox. A failed Actions
run also sends the "run failed" mail, which is the closest thing GitHub offers to an
alert at the moment the card moves. The failure is the notification channel, not a
broken build - nothing downstream depends on this job.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# The shared reader lives in the pipeline's scripts folder (S-1.75).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from open_questions import find_section, open_questions  # noqa: E402

REPO = os.environ["GITHUB_REPOSITORY"]
WARN_LABEL = "has-open-questions"
REVIEW_STATUS = "status:in-review"
# In-review first: that is where the warning can still stop a merge.
GATED_STATUSES = (REVIEW_STATUS, "status:done")
COMMENT_MARKER = "<!-- open-questions-gate -->"


def gh(*args: str, **kwargs: object) -> str:
    """Run the gh CLI and return its stdout; exit the run when it fails."""
    out = subprocess.run(
        ("gh",) + args, capture_output=True, text=True, encoding="utf-8", **kwargs
    )
    if out.returncode != 0:
        sys.exit("gh {} failed: {}".format(" ".join(args), out.stderr.strip()))
    return out.stdout


def gated_status(labels: list[str]) -> str | None:
    """The status label that puts the issue under the gate, or None when none does."""
    return next((s for s in GATED_STATUSES if s in labels), None)


def warning(heading: str, questions: list[str]) -> str:
    """The gate comment. `heading` is the section title as the issue spells it."""
    listed = "\n".join(f"- {q}" for q in questions)
    return (
        f"## ⚠️ עבר ל-`{REVIEW_STATUS}` עם שאלות פתוחות\n\n"
        f"ב-issue הזה יש {len(questions)} שאלות שעדיין לא נסגרו:\n\n{listed}\n\n"
        f'אם הן נענו — לסמן אותן בסעיף "{heading}" (`- [x]`) ולהוסיף את ההחלטה '
        f"לצד כל אחת. הסטטוס **לא** שונה, והתווית `{WARN_LABEL}` תרד "
        "אוטומטית ברגע שכולן מסומנות."
    )


def upsert_comment(number: str, text: str) -> None:
    """One gate comment per issue, edited in place: a rerun must not spam the thread."""
    # --slurp: --paginate alone prints one JSON array per page, which json.loads
    # cannot read past 30 comments (claude-config #164).
    raw = gh("api", f"repos/{REPO}/issues/{number}/comments", "--paginate", "--slurp")
    comments = [c for page in json.loads(raw) for c in page]
    existing = next((c for c in comments if COMMENT_MARKER in (c["body"] or "")), None)
    path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8", newline="\n"
        ) as fh:
            fh.write(text + "\n\n" + COMMENT_MARKER + "\n")
            path = fh.name
        if existing:
            gh(
                "api",
                "--method",
                "PATCH",
                "repos/{}/issues/comments/{}".format(REPO, existing["id"]),
                "-F",
                "body=@" + path,
            )
        else:
            gh("issue", "comment", str(number), "--repo", REPO, "--body-file", path)
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


def main() -> int:
    """Check the issue in ISSUE_NUMBER; 1 when it is gated with open questions."""
    number = os.environ.get("ISSUE_NUMBER")
    if not number:
        sys.exit("ISSUE_NUMBER is not set")

    issue = json.loads(
        gh("issue", "view", number, "--repo", REPO, "--json", "body,labels")
    )
    labels = [lb["name"] for lb in issue["labels"]]

    status = gated_status(labels)
    if status is None:
        print(f"#{number} is not in review or done - nothing to check.")
        return 0

    questions = open_questions(issue["body"])

    if not questions:
        print(f"#{number} reached {status} with no open questions.")
        if WARN_LABEL in labels:
            gh("issue", "edit", number, "--repo", REPO, "--remove-label", WARN_LABEL)
            upsert_comment(
                number, "✅ אין יותר שאלות פתוחות ב-issue הזה. האזהרה הוסרה."
            )
        return 0

    if status != REVIEW_STATUS:
        # Merged already: Dolev chose to merge with the box open, a new mail is noise.
        print(f"#{number} is merged with {len(questions)} open question(s).")
        return 0

    upsert_comment(number, warning(find_section(issue["body"])[0], questions))

    if WARN_LABEL not in labels:
        gh("issue", "edit", number, "--repo", REPO, "--add-label", WARN_LABEL)

    # Deliberate failure - this is the mail, not a broken build (module docstring).
    print(f"#{number} has {len(questions)} open question(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
