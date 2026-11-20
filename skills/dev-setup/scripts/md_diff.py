"""Prints a `diff` block for each Markdown file a branch changed, for the chat (S-1.65).

The message that asks Dolev to approve a change (a spec hand-off, a hand-off for review,
the orchestrator's message before the merge window) shows the change itself for every
`.md` file, like git does. Code files are left out: the change map and the link to the
PR's changes hold them. The rule, and where in the message the blocks go:
reference/chat-decisions.md, "ה-diff של קובצי MD בהודעה שלפני אישור".

    python md_diff.py --base origin/main --head HEAD --pr-url <the PR's /files link>

It reads git, not the GitHub API: GraphQL is blocked in the cloud, and the REST `patch`
of a large file is cut. Prints nothing when no `.md` file changed. When git cannot be
read it prints one sentence with the link and still exits 0: the hand-off and the merge
never stop on it.
"""

import argparse
import subprocess
import sys
from dataclasses import dataclass

LINE_LIMIT = 150


@dataclass(frozen=True)
class Change:
    """One changed Markdown file: its git status letter, the path before and after."""

    status: str
    old: str
    new: str


def git(*args: str) -> subprocess.CompletedProcess | None:
    """Runs git and returns the result, or None when git itself cannot start.

    Paths are literal (a `*` in a file name is not a glob), and bytes that are not
    UTF-8 are replaced, so an odd file never turns into a traceback.
    """
    try:
        return subprocess.run(
            ["git", "--literal-pathspecs", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return None


def parse_name_status(output: str) -> list[Change]:
    """The changes in `git diff --name-status -M -z` output, in git's order.

    `-z` keeps a path with a space or a non-ASCII name as it is, and a rename carries
    two paths (the rule in .claude/CLAUDE.md, as in size_check.py).
    """
    fields = output.split("\0")
    changes, i = [], 0
    while i < len(fields) - 1:
        status = fields[i][:1]
        if status in ("R", "C"):
            changes.append(Change(status, fields[i + 1], fields[i + 2]))
            i += 3
        else:
            changes.append(Change(status, fields[i + 1], fields[i + 1]))
            i += 2
    return changes


def is_markdown(change: Change) -> bool:
    """Whether either side of the change is a `.md` file."""
    return change.old.lower().endswith(".md") or change.new.lower().endswith(".md")


def body_lines(patch: str) -> list[str]:
    """The hunks of one file's patch: everything from the first `@@`.

    git's header lines (`diff --git`, `index`, `---`, `+++`) are left out, since the
    heading above the block replaces them.
    """
    lines = patch.split("\n")  # not splitlines(): git ends lines with \n only
    if lines and not lines[-1]:
        lines.pop()
    starts = (i for i, line in enumerate(lines) if line.startswith("@@"))
    return lines[next(starts, len(lines)) :]


def heading(change: Change) -> str:
    """The Hebrew line above a block. It opens with a Hebrew word, so it reads RTL."""
    if change.status == "A":
        return f"קובץ חדש: `{change.new}`"
    if change.status == "D":
        return f"קובץ שנמחק: `{change.old}`"
    if change.status == "R":
        return f"שם שונה: `{change.old}` ← `{change.new}`"
    return f"הקובץ `{change.new}`"


def fence_for(lines: list[str]) -> str:
    """A fence longer than any backtick run in the block, so it never closes early."""
    longest = 0
    for line in lines:
        run = 0
        for char in line:
            run = run + 1 if char == "`" else 0
            longest = max(longest, run)
    return "`" * max(3, longest + 1)


def block(title: str, lines: list[str]) -> str:
    """One file: the heading, then its lines in a `diff` block."""
    fence = fence_for(lines)
    return "\n".join([title, "", f"{fence}diff", *lines, fence])


Patch = tuple[Change, list[str]]


def render(patches: list[Patch], pr_url: str, limit: int = LINE_LIMIT) -> str:
    """All the blocks, up to `limit` diff lines in all, then the cut sentence."""
    out, used, cut, skipped = [], 0, None, []
    for change, lines in patches:
        if not lines:  # a pure rename, an empty file, a mode change or a binary file
            out.append(heading(change))
            continue
        if used >= limit:
            skipped.append(change.new)
            continue
        room = limit - used
        if len(lines) > room:
            cut = change.new
            lines = lines[:room]
        out.append(block(heading(change), lines))
        used += len(lines)
    if cut or skipped:
        out.append(cut_sentence(cut, skipped, pr_url, limit))
    return "\n\n".join(out)


def cut_sentence(cut: str | None, skipped: list[str], pr_url: str, limit: int) -> str:
    """The sentence after a cut: which files are partial or missing, and the link."""
    parts = [f"ה-diff נחתך ב-{limit} שורות."]
    if cut:
        parts.append(f"הקובץ `{cut}` הוצג בחלקו.")
    if skipped:
        names = ", ".join(f"`{name}`" for name in skipped)
        parts.append(f"לא הוצגו: {names}.")
    parts.append(f"ההמשך בשינויים ב-PR: {pr_url}" if pr_url else "ההמשך בשינויים ב-PR.")
    return "\n\n".join(parts)


def unreadable(pr_url: str) -> str:
    """The one sentence when git could not be read; the hand-off goes on."""
    link = f" השינויים ב-PR: {pr_url}" if pr_url else ""
    return f"ה-diff של קובצי ה-MD לא נקרא.{link}"


def file_patch(
    base: str, head: str, change: Change
) -> subprocess.CompletedProcess | None:
    """The patch of one file between the two refs, with renames followed."""
    paths = [change.old] if change.old == change.new else [change.old, change.new]
    return git("diff", "-M", "--no-color", f"{base}...{head}", "--", *paths)


def collect(base: str, head: str) -> list[Patch] | None:
    """Each changed Markdown file with its diff lines, or None when git failed."""
    listing = git("diff", "--name-status", "-M", "-z", f"{base}...{head}")
    if listing is None or listing.returncode != 0:
        return None
    patches = []
    for change in filter(is_markdown, parse_name_status(listing.stdout)):
        patch = file_patch(base, head, change)
        if patch is None or patch.returncode != 0:
            return None
        patches.append((change, body_lines(patch.stdout)))
    return patches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base", required=True, help="the default branch, e.g. origin/main"
    )
    parser.add_argument("--head", default="HEAD", help="the branch of the PR")
    parser.add_argument("--pr-url", default="", help="the link to the PR's changes")
    args = parser.parse_args(argv)
    patches = collect(args.base, args.head)
    text = unreadable(args.pr_url) if patches is None else render(patches, args.pr_url)
    if text:
        print(text)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
