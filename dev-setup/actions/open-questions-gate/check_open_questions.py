"""Warn when an issue reaches `status:done` while it still has open questions.

Why this exists
---------------
`status:done` means "approved - ready to merge". Reaching it with a question still
unanswered means the review passed over something, and once the issue is merged and
closed it stops being visible: sync_project.py drops closed issues that lack
`status:done` off the board entirely, and the ones that carry it land in Done, where
nobody re-reads the thread.

What counts as an open question
-------------------------------
The `## שאלות פתוחות` (or `Open questions`) section of the issue body is the single source of truth. Inside it:

    - [ ] question           -> open
    - [x] question - הוחלט:  -> resolved, kept for the record

A section that contains **no checkbox at all** pre-dates the convention (twelve issues did
when this was written). There, every non-empty line counts as an open question, bullet or
prose alike - #45's section is a paragraph with a real unanswered question in it and no
bullet to hang the rule on. That is deliberately generous: a false warning costs a glance,
a missed question costs a wrong merge, and the way to make it precise is to add the
checkboxes. One checkbox anywhere in the section switches it to the exact rule.

Questions asked in comments do not count - the Plan phase copies them into the section, so
this stays one parse of one place.

Why it fails the run
--------------------
An issue comment alone is easy to miss in a busy notification inbox. A failed Actions run
also sends the "run failed" mail, which is the closest thing GitHub offers to an alert at
the moment the card moves. The failure is the notification channel, not a broken build -
nothing downstream depends on this job.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.environ["GITHUB_REPOSITORY"]
WARN_LABEL = "has-open-questions"
DONE_LABEL = "status:done"
COMMENT_MARKER = "<!-- open-questions-gate -->"

HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s*(.+?)\s*#*\s*$")
SECTION_TITLES = ("שאלות פתוחות", "open questions")
UNCHECKED_RE = re.compile(r"^\s*[-*+]\s*\[\s\]\s*(.+?)\s*$")
CHECKED_RE = re.compile(r"^\s*[-*+]\s*\[[xX]\]\s*")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")
# "_טרם נכתבה תוכנית._" and friends - a template placeholder, not a question.
PLACEHOLDER_RE = re.compile(r"^\s*[_*].*[_*]\s*$")
# The section is the last one in the body, so the hidden sync marker falls inside it.
COMMENT_RE = re.compile(r"^\s*<!--.*-->\s*$")


def gh(*args, **kwargs):
    out = subprocess.run(
        ("gh",) + args, capture_output=True, text=True, encoding="utf-8", **kwargs
    )
    if out.returncode != 0:
        sys.exit("gh %s failed: %s" % (" ".join(args), out.stderr.strip()))
    return out.stdout


def find_section(body):
    """(heading, lines) of the open-questions section, or None if there is no such section.

    The heading comes back as written, so the warning names the section the way the repo
    spells it (business-plan-generator writes "Open questions").

    A plan may carry its own "open questions" subsection, which comes before the issue's
    section - so the first match is the wrong one (Osea #1, 24.10.2026: the plan's "אין."
    line was read as an open question). The issue's section is always the last one, both in
    bodies written with `##` and in issue-form bodies, where every field is `###`. It ends at
    the next heading of the same or a higher level.
    """
    lines = (body or "").splitlines()
    headings = [(i, len(m.group(1)), m.group(2).strip())
                for i, m in ((i, HEADING_RE.match(l)) for i, l in enumerate(lines)) if m]
    matches = [(i, level, title) for i, level, title in headings
               if any(t in title.lower() for t in SECTION_TITLES)]
    if not matches:
        return None
    start, level, title = matches[-1]
    end = next((i for i, lv, _ in headings if i > start and lv <= level), len(lines))
    return title, lines[start + 1:end]


def open_questions(body):
    section = find_section(body)
    if section is None:
        return []
    lines = section[1]
    structured = any(UNCHECKED_RE.match(l) or CHECKED_RE.match(l) for l in lines)
    found = []
    for line in lines:
        if (not line.strip() or CHECKED_RE.match(line) or PLACEHOLDER_RE.match(line)
                or COMMENT_RE.match(line)):
            continue
        m = UNCHECKED_RE.match(line)
        if m:
            found.append(m.group(1))
        elif not structured:
            # Legacy section - no checkbox to key on, so take the line as it stands.
            m = BULLET_RE.match(line)
            found.append(m.group(1) if m else line.strip())
    return found


def warning(heading, questions):
    """The gate comment. `heading` is the section title as the issue spells it."""
    listed = "\n".join("- %s" % q for q in questions)
    return (
        "## ⚠️ עבר ל-`status:done` עם שאלות פתוחות\n\n"
        "ב-issue הזה יש %d שאלות שעדיין לא נסגרו:\n\n%s\n\n"
        "אם הן נענו — לסמן אותן בסעיף \"%s\" (`- [x]`) ולהוסיף את ההחלטה "
        "לצד כל אחת. הסטטוס **לא** שונה, והתווית `%s` תרד אוטומטית ברגע שכולן מסומנות."
    ) % (len(questions), listed, heading, WARN_LABEL)


def upsert_comment(number, text):
    """One gate comment per issue, edited in place - a rerun must not spam the thread."""
    raw = gh("api", "repos/%s/issues/%s/comments" % (REPO, number), "--paginate")
    existing = next((c for c in json.loads(raw) if COMMENT_MARKER in (c["body"] or "")), None)
    path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8", newline="\n"
        ) as fh:
            fh.write(text + "\n\n" + COMMENT_MARKER + "\n")
            path = fh.name
        if existing:
            gh("api", "--method", "PATCH",
               "repos/%s/issues/comments/%s" % (REPO, existing["id"]),
               "-F", "body=@" + path)
        else:
            gh("issue", "comment", str(number), "--repo", REPO, "--body-file", path)
    finally:
        if path and os.path.exists(path):
            os.unlink(path)


def main():
    number = os.environ.get("ISSUE_NUMBER")
    if not number:
        sys.exit("ISSUE_NUMBER is not set")

    issue = json.loads(gh("issue", "view", number, "--repo", REPO, "--json", "body,labels"))
    labels = [lb["name"] for lb in issue["labels"]]

    if DONE_LABEL not in labels:
        print("#%s is not %s - nothing to check." % (number, DONE_LABEL))
        return 0

    questions = open_questions(issue["body"])

    if not questions:
        print("#%s reached %s with no open questions." % (number, DONE_LABEL))
        if WARN_LABEL in labels:
            gh("issue", "edit", number, "--repo", REPO, "--remove-label", WARN_LABEL)
            upsert_comment(number, "✅ אין יותר שאלות פתוחות ב-issue הזה. האזהרה הוסרה.")
        return 0

    upsert_comment(number, warning(find_section(issue["body"])[0], questions))

    if WARN_LABEL not in labels:
        gh("issue", "edit", number, "--repo", REPO, "--add-label", WARN_LABEL)

    # Deliberate failure - this is the mail, not a broken build. See the module docstring.
    print("#%s has %d open question(s)." % (number, len(questions)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
