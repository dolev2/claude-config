---
name: dev-ship
description: Ships a finished branch in the current repo end to end — commits outstanding work, rebases onto the default branch, runs the test suite, opens a PR, waits for CI, squash-merges it, moves the linked issue to status:done so the board lands it in Done, and cleans up the branch. This is the pipeline's only merge path: an issue in status:in-review merges when Dolev asks for it in the chat ("תמזג את #12"). Use in any of Dolev's repos whenever he asks to ship, merge and clean up, finish or close out a branch, or to merge a specific issue ("תשחרר", "תמזג ותנקה", "תמזג את #N", "ship it"). Works with or without the pipeline labels (without them it skips the issue step). Prefer this over the generic pr-ship skill; if the repo has its own repo-specific ship skill, use that instead.
---

# Ship a branch

Runs the whole tail of a change in one go: rebase onto the default branch → tests → PR → CI
→ open questions → squash-merge → issue to `status:done` → cleanup. None of these happen if an earlier one
fails. Do not skip or reorder the steps, and stop the moment one of them fails.

## Step 0: Orient

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

- `repo_skills` lists a repo-specific ship skill? Use it instead.
- Note `default_branch` (written `<default>` below; never assume `main` or `master`).
- In a cloud session (`CLAUDE_CODE_REMOTE=true`), run every `gh` command below through the table in `reference/cloud.md`.
- `ready` tells whether step 6 applies. Without the pipeline labels, this is a plain ship
  and step 6 is skipped. Do not offer `dev-setup` here; shipping does not need it.

Read in `$HOME/.claude/skills/dev-setup/reference/`: `tests.md`, `git-flow.md` and `review-app.md`
(step 7 stops the branch's review app, if one runs). If the pipeline is installed, also
`pipeline.md` (the label vocabulary and the exclusivity rule), which step 6 depends on,
`issue-body.md` (the open-questions section, step 4c), and `after-merge.md` (step 8).

## Relationship to dev-code

This skill is the **only merge path**. `dev-code` opens the PR and leaves the issue in
`status:in-review`; Dolev reviews it and asks for the merge in the chat ("תמזג את #N"). That
request *is* the go-ahead (GitHub does not let him Approve a PR opened from his own account),
so no second confirmation is needed. Still, never ship an issue Dolev has not asked about.
`status:done` is set here, after the merge, and means "merged", never "approved".

## Step 0b: Entry from an issue (pipeline repos only)

When Dolev names an issue rather than a branch:

1. Find its open PR: the PRs that close it (`Closes #<I>`), of which the open one.
   ```bash
   for P in $(gh issue view <I> --json closedByPullRequestsReferences \
                --jq '.closedByPullRequestsReferences[].number'); do
     gh pr view "$P" --json number,state,headRefName --jq 'select(.state=="OPEN")'
   done
   ```
   None: say so and stop; there is nothing to merge. More than one: list them and ask which.
   The issue is normally in `status:in-review`; another status is not a reason to stop, since
   Dolev asked by name, but say so in the summary.
2. Work on the PR's branch (`headRefName`) in a worktree, never by switching branches in the
   shared working copy. The worktree `dev-code` left for that issue is the one to use: it
   holds the review app (`git worktree list` shows it). In a cloud session there is no
   worktree: check out the branch in the session's own clone (`reference/git-flow.md`). Then go on
   to step 1.

## Step 1: Sanity checks

1. If you are on `<default>`, or in a cloud session on a branch the service named for the
   session rather than the issue's branch (`reference/git-flow.md`), do not ship from it. If there is nothing to ship at all (clean
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

As `reference/tests.md` says: the commands in the repo's `CLAUDE.md`, plus any
conditional suite whose area the diff touches (`git diff --name-only origin/<default>...HEAD`),
or the manual check a suite-less repo defines there. The lint runs first, then the suites of
different areas at the same time, in one Bash command ("מתי רץ מה" there). A retry after a fix
reruns the lint and the full suite of the area the fix touched. No commands in CLAUDE.md? Use what the CI
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

## Step 4c: Open questions (pipeline repos only)

Skip this step when `ready` was `False`. It runs on every pipeline merge, whether Dolev named
the issue or the branch:

```bash
gh pr view <N> --json closingIssuesReferences --jq '.closingIssuesReferences[].number'
```

For each issue, read its "שאלות פתוחות" section (`issue-body.md`). A box still unticked: list
it and ask Dolev whether to merge anyway; stop until he answers. Do not tick boxes on his
behalf. The open-questions gate already warned when the issue moved to `status:in-review`;
this is the last look before the merge.

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

No `--subject` (a hook blocks it): GitHub titles the commit with the PR title plus `(#N)`,
once the repo's squash title setting is `PR_TITLE` (`dev-setup`, step 5). If the PR title looks
wrong, fix it first (`gh pr edit <N> --title "<title>"`) and tell Dolev. Never write the
subject by hand, and never add a task number (like `15ב.`) that the issue or PR title does not
already carry: a commit title on `<default>` cannot be fixed without rewriting history.

In a cloud session `gh pr merge` does not run (`reference/cloud.md`). Merge with
`mcp__github__merge_pull_request`: `merge_method: "squash"`, `expectedHeadSha` set to the head
that steps 3–4b checked, and no `commit_title` (a hook blocks it, like `--subject`). The
branch on GitHub is deleted by the repo's "Automatically delete head branches" setting, in
place of `--delete-branch`.

Either way, this pops an approval window for Dolev: an `ask` rule in `~/.claude/settings.json`
for `gh pr merge`, and `hooks/ask_before_merge.py` for every other way to merge. That is
expected. If he declines it, stop and report which step you stopped at; never merge another
way.

If the merge is blocked (required reviews, protection, conflicts), stop and report the exact
reason `gh` or the MCP tool gives. Do not retry blindly and do not force anything. `--delete-branch` may fail
where the harness blocks destructive git operations; that is expected. Never fall back to
deleting branches by hand.

## Step 6: Move the linked issue to Done (pipeline repos only)

Skip this step when `ready` was `False`.

Every merged issue comes from `status:in-review`, and `status:done` is what says "merged".
The sync adds it too once the issue closes as completed, but only on its next run; setting it
here makes the board right at once.

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

The open questions were checked before the merge (step 4c); a box ticked or not, the issue is
merged now, and `status:done` says exactly that. If the issue already carries `status:done`
(the sync got there first, after the issue closed), the command is a no-op and that is
correct; verify rather than assume.

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
`<default>` in it, as `reference/git-flow.md` says; delete the branch after the
worktree is removed (git refuses to delete a branch checked out in a worktree).

In a cloud session there is no worktree to remove, and `<default>` is not checked out:
instead of the first line above, run `git fetch origin <default>` and then
`git checkout --detach origin/<default>` (without the fetch, that is `<default>` before the
merge). `git status` then shows a detached HEAD at `origin/<default>`, which is expected.
Then delete the local branch as above. Never delete the remote branch with `git push`: the proxy blocks it,
and the repo setting deletes it; the `git ls-remote` check still applies
(`reference/git-flow.md`).

If the branch has a review app (`review-app.json` names it), stop it before removing its
worktree, as `reference/review-app.md` says.

## Step 8: Offer a session for the next issue (pipeline repos only)

Only after the merge and the cleanup both succeeded. Follow `reference/after-merge.md`: pick the next issue the way `dev-next` does, without routing it,
and offer it as a session card whose opening prompt is `תחקור את #<N>` or `תקודד את #<N>`.
The decision that matters is fresh session versus fork; the doc holds the rule. Never start
that issue in this session.

## Reporting back

One short summary in Hebrew: the PR link and title, the merge method, which issue moved to `status:done` (or that
the PR closed none, or that the repo has no pipeline), and whether both branches are gone. If
you stopped early, say exactly which step and why. End with the next-issue offer from step 8:
which issue, fresh or fork and why in one line, or what the sprint waits for.
