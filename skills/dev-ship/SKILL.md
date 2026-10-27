---
name: dev-ship
description: Ships a finished branch in the current repo end to end — commits outstanding work, rebases onto the default branch, runs the test suite, opens a PR, waits for CI, squash-merges it, moves the linked issue to status:done so the board lands it in Done, and cleans up the branch. Use in any of Dolev's repos whenever he asks to ship, merge and clean up, finish or close out a branch ("תשחרר", "תמזג ותנקה", "ship it"). Works with or without the pipeline labels (without them it skips the issue step). Prefer this over the generic pr-ship skill; if the repo has its own repo-specific ship skill, use that instead.
---

# Ship a branch

Runs the whole tail of a change in one go: rebase onto the default branch → tests → PR → CI
→ squash-merge → issue to `status:done` → cleanup. None of these happen if an earlier one
fails. Do not skip or reorder the steps, and stop the moment one of them fails.

## Step 0: Orient

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

- `repo_skills` lists a repo-specific ship skill? Use it instead.
- Note `default_branch` (written `<default>` below; never assume `main` or `master`).
- `ready` tells whether step 6 applies. Without the pipeline labels, this is a plain ship
  and step 6 is skipped. Do not offer `dev-setup` here; shipping does not need it.

If the pipeline is installed, the label vocabulary and the exclusivity rule are in
`$HOME/.claude/skills/dev-setup/reference/pipeline.md`. Step 6 depends on them.

## Relationship to dev-code

`dev-code` Part B is the **review-first** merge path: Dolev already reviewed the PR and set
`status:done`, and the merge happens on his explicit request for that issue. This skill is the
**ship-what-is-in-front-of-me** path: asking for it *is* the go-ahead, so no second
confirmation is needed. Still, never ship an issue Dolev has not asked about.

## Step 1: Sanity checks

1. If you are on `<default>`, do not ship from it. If there is nothing to ship at all (clean
   tree and `<default>` not ahead of `origin/<default>`), say so and stop. Otherwise cut a
   feature branch off the current state first: `claude/issue-<N>-<slug>` when the work belongs
   to an issue, otherwise a name after what actually changed (`fix/lead-duplicate-webhook`,
   `docs/pipeline-stages`), never a placeholder.
2. `git status`. Commit anything outstanding rather than pausing for approval: read `git diff`
   (and `git diff --cached`) so the message describes the real change, then `git add -A` and
   commit in the repo's style, with the `Co-Authored-By` line the session is configured with.
   The one case worth stopping for is a diff that mixes unrelated work or carries debug
   leftovers (stray `print`/`console.log`, commented-out code): flag those instead.

Do not push yet; step 2 rewrites the commits.

## Step 2: Rebase onto the default branch

Do this **before** the tests. Several sessions may work on the repo at once, so a branch that
is green locally can still be several merges behind.

```bash
git fetch origin <default>
git rebase origin/<default>
```

Rebase, never merge. **If the rebase reports a conflict, stop here.** No tests, no PR. Report
which files conflict and ask whether to resolve them; `git rebase --abort` puts the branch
back as it was. Never resolve a conflict by taking one side wholesale.

Then push: `git push -u origin <branch>` for a new branch, or `git push --force-with-lease`
for one that was already on the remote. Never a plain `--force`.

## Step 3: Run the tests

As the reference doc's "בדיקות" says: the commands in the repo's `CLAUDE.md`, plus any
conditional suite whose area the diff touches (`git diff --name-only origin/<default>...HEAD`),
or the manual check a suite-less repo defines there. No commands in CLAUDE.md? Use what the CI
workflow runs. Neither? Ask Dolev which command proves the change, rather than shipping
untested.

**Failing to run the tests is not permission to skip them.** Missing dependencies get
installed, not skipped. **If any test fails, stop here.** Report the failing tests and output,
and ask whether to fix and retry.

## Step 4: Open the PR, or reuse the open one

```bash
gh pr list --head <branch> --state open --json number,url
```

A PR is already open for this branch: use it (the push in step 2 updated it). Otherwise:

```bash
gh pr create --base <default> --fill
```

`--base` is explicit on purpose. If the commit messages are terse or the diff is large, write
the body yourself with `--title` / `--body-file`. When the work belongs to a tracked issue,
the body must contain `Closes #<N>`: that links the PR and closes the issue on merge, and
step 6 reads the link back.

## Step 4b: Wait for CI

```bash
gh pr checks <N> --watch --fail-fast
```

**If a check fails, stop here.** Report which job failed and link the run. A private repo on
a free plan has no branch protection, so a red PR still has a working merge button; this step
is the only thing between a red run and `<default>`. If the repo reports no checks at all,
say so and continue on the strength of step 3.

## Step 5: Squash-merge

First confirm it still merges cleanly:

```bash
gh pr view <N> --json mergeable,mergeStateStatus
```

Anything other than `MERGEABLE` (`UNKNOWN` right after a push: wait a few seconds and ask
again): back to step 2, then the tests and CI again. Then:

```bash
gh pr merge <N> --squash --delete-branch
```

If the merge is blocked (required reviews, protection, conflicts), stop and report the exact
reason `gh` gives. Do not retry blindly and do not force anything. `--delete-branch` may fail
where the harness blocks destructive git operations; that is expected. Never fall back to
deleting branches by hand.

## Step 6: Move the linked issue to Done (pipeline repos only)

Skip this step when `ready` was `False`.

Not cosmetic: `sync_project.py` skips any **closed** issue that does not carry `status:done`,
treating it as "closed as not-planned". An issue merged while still on `status:in-review`
drops off the board silently.

```bash
gh pr view <N> --json closingIssuesReferences --jq '.closingIssuesReferences[].number'
```

Empty output: the PR closes no issue. Say so and move on. Otherwise, for each issue, swap the
status label in a single command (`status:*` is exclusive):

```bash
CUR=$(gh issue view <I> --json labels \
        --jq '[.labels[].name | select(startswith("status:"))] | map("--remove-label=" + .) | .[]')
gh issue edit <I> --add-label "status:done" $CUR
```

Before setting the label, check the issue's "שאלות פתוחות" section. If a box is still
unticked, say so and ask Dolev whether to go ahead. Do not tick boxes on his behalf.

Leave `owner:*` alone. If the issue already carries `status:done` (the `dev-code` path), the
command is a no-op and that is correct; verify rather than assume.

## Step 7: Clean up locally

```bash
git checkout <default> && git pull --ff-only   # skip if <default> is checked out in another worktree
git fetch --prune
git status --short --branch     # expect: <default>, in sync with origin/<default>
git ls-remote --heads origin <branch>   # expect: no output
```

Then delete the local branch. `git branch -d` always refuses after a squash merge (the squash
commit has a new SHA, so git sees the branch as unmerged), so check the merge yourself and use
`-D` only when the local tip is exactly what was merged:

```bash
MERGED=$(gh pr view <N> --json state,headRefOid --jq 'select(.state=="MERGED") | .headRefOid')
[ -n "$MERGED" ] && [ "$(git rev-parse <branch>)" = "$MERGED" ] && git branch -D <branch>
```

If the tips differ, the local branch has commits that were never merged: leave it and say so.
`git pull` does not delete local branches, and `git fetch --prune` only removes `origin/*`
refs, so without this step the local branch stays forever.

When this ran inside a worktree the session owns, leave that worktree instead of checking out
`<default>` in it, as the reference doc's "עותק העבודה" says; delete the branch after the
worktree is removed (git refuses to delete a branch checked out in a worktree).

If the branch has a review app (`review-app.json` names it), stop it before removing its
worktree, as the reference doc's "הרמה לסקירה" says.

## Reporting back

One short summary in Hebrew: the PR link and title, the merge method, which issue moved to `status:done` (or that
the PR closed none, or that the repo has no pipeline), and whether both branches are gone. If
you stopped early, say exactly which step and why.
