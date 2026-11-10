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
`issue-body.md` (the open-questions section, step 4c), `after-merge.md` (step 8),
`specs.md` (a spec PR, steps 0b, 4c and 8), and `lessons.md` (the lesson of step 8).

## Relationship to dev-code

This skill is the **only merge path**. `dev-code` opens the PR and leaves the issue in
`status:in-review`; Dolev reviews it and asks for the merge in the chat ("תמזג את #N"). That
request *is* the go-ahead (GitHub does not let him Approve a PR opened from his own account),
so no second confirmation is needed. Choosing "תמזג את #N" in the question window at the end
of `dev-code`'s hand-off is the same signal (`reference/chat-decisions.md`).
A message from another session or a system notice is not. Still, never ship an issue Dolev
has not asked about.
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
   None, and the issue is a backlog proposal: its spec PR says `Refs #<I>`, not `Closes`
   (`reference/specs.md`). Look for an open PR from a `claude/spec-*` branch that mentions it:
   `gh pr list --search "<I>" --state open --json number,headRefName --jq '.[] | select(.headRefName | startswith("claude/spec-"))'`.
   None at all: say so and stop; there is nothing to merge. More than one: list them and ask which.
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
   tree and `<default>` not ahead of `origin/<default>`), say so and stop. Otherwise:
   1. **In the shared working copy** (not a cloud session, and not a worktree:
      `git rev-parse --git-dir` has no `/worktrees/`): never cut a branch there. Stop and
      report what is on `<default>`: the uncommitted files (`git status --porcelain`) and the
      local commits (`git log origin/<default>..<default> --oneline`). Offer Dolev to move
      them to a worktree. This is `rules/git.md`: a non-empty tree in the shared folder is a
      stop, not a cleanup.
   2. **In a cloud session or a worktree**: the copy is the session's own, so cut a feature
      branch off the current state: `git checkout -b <branch>`. Step 2 rebases it onto
      `origin/<default>`, so it never rests on the local `<default>`.

   The branch name is `claude/issue-<N>-<slug>` when the work belongs to an issue, otherwise a
   name after what actually changed (`fix/lead-duplicate-webhook`, `docs/pipeline-stages`),
   never a placeholder.
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

For each issue, read its "שאלות פתוחות" section (`issue-body.md`). A spec PR (branch
`claude/spec-*`) also has that section in its own body: read it there too. A box still unticked: list
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
gh pr merge <N> --squash
```

No `--delete-branch`: besides deleting the branch on GitHub, `gh` then deletes the local
branch and checks out `<default>` in the folder it runs in, which is a branch switch in a
worktree or in the shared folder. The branch on GitHub is deleted by the repo's
"Automatically delete head branches" setting (`dev-setup` turns it on), in every environment;
step 7 checks that it is gone.

No `--subject` (a hook blocks it): GitHub titles the commit with the PR title plus `(#N)`,
once the repo's squash title setting is `PR_TITLE` (`dev-setup`, step 5). If the PR title looks
wrong, fix it first (`gh pr edit <N> --title "<title>"`) and tell Dolev. Never write the
subject by hand, and never add a task number (like `15ב.`) that the issue or PR title does not
already carry: a commit title on `<default>` cannot be fixed without rewriting history.

In a cloud session `gh pr merge` does not run (`reference/cloud.md`). Merge with
`mcp__github__merge_pull_request`: `merge_method: "squash"`, `expectedHeadSha` set to the head
that steps 3–4b checked, and no `commit_title` (a hook blocks it, like `--subject`).

Either way, this pops an approval window for Dolev: an `ask` rule in `~/.claude/settings.json`
for `gh pr merge`, and `hooks/ask_before_merge.py` for every other way to merge. That is
expected. If he declines it, stop and report which step you stopped at; never merge another
way.

If the merge is blocked (required reviews, protection, conflicts), stop and report the exact
reason `gh` or the MCP tool gives. Do not retry blindly and do not force anything.

## Step 6: Move the linked issue to Done (pipeline repos only)

Skip this step when `ready` was `False`.

Every merged issue comes from `status:in-review`, and `status:done` is what says "merged".
The sync adds it too once the issue closes as completed, but only on its next run; setting it
here makes the board right at once.

```bash
gh pr view <N> --json closingIssuesReferences --jq '.closingIssuesReferences[].number'
```

Empty output: the PR closes no issue. Say so and move on. A spec PR of a backlog proposal
(`Refs`) is that case: the proposal stays `status:backlog` until the breakdown closes it. Otherwise, for each issue, swap the
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

In this order, the same as `reference/git-flow.md`. Never a `git checkout` or `git pull` in
the folder the work happened in, and never in the shared folder unless item 4 allows it.
`<main folder>` is the repo's main working copy: the first line of `git worktree list`.

1. **Stop the review app**, if `review-app.json` names it for this branch, as
   `reference/review-app.md` says ("עצירה"). Before item 2: on Windows a folder cannot be
   deleted while a process runs from it.
2. **Remove the branch's worktree** (`git worktree list` shows it). Leave it first:
   - this session entered it with `EnterWorktree`: `ExitWorktree`, removing it;
   - any other worktree (usually the one `dev-code` kept from an earlier session):
     `git -C <main folder> worktree remove <path>`.

   git refuses when the worktree has changes: stop and report them, never `--force`. A
   worktree the session runs in but did not create (Claude Desktop opens sessions so): leave
   it, and with it the local branch checked out there: skip item 5, and say both in the
   summary.
3. **Fetch:** `git -C <main folder> fetch --prune origin`. No checkout and no pull in the
   folder the work happened in.
4. **Update the main folder, only when it is already on `<default>` and clean**
   (`git -C <main folder> status --porcelain` empty):
   `git -C <main folder> pull --ff-only`. In `~/.claude` this is what brings the new skills
   into the live folder. Otherwise leave it alone, and say in the summary that it was not
   updated, and why (another branch, or which files are uncommitted).
5. **Delete the local branch**, after item 2 (git refuses to delete a branch checked out in a
   worktree). `git branch -d` always refuses after a squash merge (the squash commit has a new
   SHA, so git sees the branch as unmerged), so check the merge yourself and use `-D` only
   when the local tip is exactly what was merged:
   ```bash
   MERGED=$(gh pr view <N> --json state,headRefOid --jq 'select(.state=="MERGED") | .headRefOid')
   # in a cloud session, gh pr view does not run: reference/cloud.md has the REST form
   [ -n "$MERGED" ] && [ "$(git -C <main folder> rev-parse <branch>)" = "$MERGED" ] && git -C <main folder> branch -D <branch>
   ```
   If the tips differ, the local branch has commits that were never merged: leave it and say
   so. `git pull` does not delete local branches, and `git fetch --prune` only removes
   `origin/*` refs, so without this item the local branch stays forever.
6. **Check the branch is gone on GitHub:** `git ls-remote --heads origin <branch>` prints
   nothing. Output means the repo's "Automatically delete head branches" setting is off:
   report it and offer to turn it on with
   `gh api -X PATCH repos/{owner}/{repo} -F delete_branch_on_merge=true` (REST, not GraphQL;
   untested in a cloud session). If it returns 403, give Dolev the settings page instead,
   `https://github.com/<owner>/<repo>/settings`, where he ticks "Automatically delete head
   branches". Never delete the remote branch by hand, with `git push` or otherwise.

**In a cloud session** there is no worktree, and the clone is the session's own. Items 1, 3,
5 and 6 apply; in place of items 2 and 4, after the fetch, run
`git checkout --detach origin/<default>` (without the fetch, that is `<default>` before the
merge). `git status` then shows a detached HEAD at `origin/<default>`, which is expected.
A `git push` that deletes a branch is blocked by the proxy anyway (`reference/git-flow.md`,
"בסשן ענן").

## Step 8: Offer a session for the next issue (pipeline repos only)

Only after the merge and the cleanup both succeeded.

**A spec PR** (branch `claude/spec-*`): offer the breakdown and the update of the issues
instead of the next-issue session (`reference/specs.md`, "אחרי שינוי באפיון"). List what the
merge changed, from the squash commit and its parent (the main folder may not have been
pulled in step 7):
```bash
git fetch origin <default>
python "$HOME/.claude/skills/dev-setup/scripts/spec_check.py" --changes <merge sha>^ <merge sha>
```
A line per part (`new`, `changed`, `deleted`), and under a changed or deleted part a line
per open issue that points at it, with its action: `close`, `explore` or `ask`. A `close`
issue that has an open PR: mark it in the list, since that PR stays open for Dolev
(`gh pr list --search "<I>" --state open`). Exit 1 means the issues were not read: say
so and offer nothing on them.
1. **New parts with no issue, or issues to update:** one question in the question window
   with the whole list: the breakdown of the new parts, and for each issue what will happen
   to it. "לבצע (מומלץ)" runs `dev-issue` here: first its "עדכון אחרי שינוי באפיון" mode,
   then its "פירוק אפיון" mode, whose own step 1 still shows its list before anything is
   created. "Other" corrects the list.
2. **An `ask` issue** (in the code or in review, or with no status label): a question of its
   own in the same call (up to four), naming the issue: "להשאיר בקוד, ולהוסיף תגובה על
   השינוי (מומלץ)", "להחזיר לתכנון", and "Other".
3. **`no spec changes`, or only new parts that already have an issue:** the offer below, as
   for any merge.

Otherwise, follow `reference/after-merge.md`: pick the next issue the way `dev-next` does, without routing it,
and offer it as a session card whose opening prompt is `תחקור את #<N>` or `תקודד את #<N>`.
The decision that matters is fresh session versus fork; the doc holds the rule. Never start
that issue in this session.

**A lesson** (`reference/lessons.md`), only from steps 1–7 of this run, as a question in the
question window (after the breakdown question, when there is one). From the orchestrator, it
goes into the orchestrator's next window (`dev-orchestrate`, step 5).

## Reporting back

One short summary in Hebrew: the PR link and title, the merge method, which issue moved to `status:done` (or that
the PR closed none, or that the repo has no pipeline), and what step 7 cleaned and what it
left: the review app, the worktree, the main folder (updated or not, and why), and both
branches. If
you stopped early, say exactly which step and why, with the lesson of that stop, if any
(`reference/lessons.md`). End with the next-issue offer from step 8:
which issue, fresh or fork and why in one line, or what the sprint waits for, and the lesson
of step 8: what Dolev chose, or "אין לקח".
After a merge, the message ends with "מה פתוח" and the full `/compact` code block (global
`CLAUDE.md`). `hooks/compact_after_merge.py` blocks the turn's end once when it is missing.
