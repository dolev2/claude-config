---
name: dev-code
description: Runs the Execute and Merge phases of Dolev's Claude-assisted GitHub pipeline in the current repo — implements issues labelled owner:claude + status:ready-to-execute or status:needs-repair, opens PRs, and merges approved work on request. Use in any of Dolev's repos whenever he asks to run/process Execute or Merge, or to implement a specific issue ("תממש את #12", "תריץ את שלב הקוד"). Works in any repo that has the pipeline labels; if the repo has its own repo-specific code skill, use that instead. Pairs with dev-plan, which handles planning.
---

# Execute & Merge phases

Part 2 of 2 of Dolev's GitHub × Claude Code pipeline (the other half is `dev-plan`). This
phase writes actual code, in a worktree, and separately merges approved work.

## Step 0: Orient

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

- `repo_skills` lists a repo-specific code skill? Use it instead.
- `ready` is `False`? Offer `dev-setup` and stop.
- Note `default_branch` (written `<default>` below), `human` (`owner:<human>`), and
  `current_sprint`.

## Read first

**`$HOME/.claude/skills/dev-setup/reference/pipeline.md`**: the label vocabulary, how to read
the full context of an issue, the Plan format, the sections "עותק העבודה" and "בדיקות", and the
branch/PR convention. Read it before step 1, every run. Then the repo's **`CLAUDE.md`**: its
working rules and its test commands.

## Part A: Execute

1. Check the WIP gate before starting a **new** issue (repairs are exempt):
   ```bash
   gh issue list --state open --label "status:in-review" --json number,title,url
   ```
   **Three or more: do not start without asking.** List them for Dolev and ask whether to go
   ahead anyway. Continue only on an explicit yes.

2. Find the work. If Dolev named a specific issue, take that one, even outside the current
   sprint (say so; never assign it a milestone). Otherwise, **inside the current sprint
   only**, repair first, then by weight:
   ```bash
   python "$HOME/.claude/skills/dev-setup/scripts/rank_issues.py" --owner claude --status needs-repair --status ready-to-execute
   ```
   An empty list means the sprint is clear. Say so and stop; never reach outside the milestone.

   **Skip blocked issues**, named or not. Take the first row, top down, without `BLOCKED by`.
   Name each row you skipped, with its open blockers, in the run summary. Do not relabel it.
   If every row is blocked, say so and stop.

   **Take exactly one issue per run.**

3. **Read the whole thread before touching code**: body (including Plan), every comment,
   every sub-issue. A `needs-repair` issue carries the reason in the newest comments; a
   sub-issue labelled `bug` is part of the same work and is fixed on the same branch unless it
   clearly stands alone. Also read what is already on the branch and in any open PR.

4. **Work in a worktree, never by switching branches in the shared working copy** (reference
   doc, "עותק העבודה"). The branch is the one the Plan names, `claude/issue-<N>-<slug>`; if it
   does not exist on the remote, create it there first
   (`git push origin origin/<default>:refs/heads/claude/issue-<N>-<slug>`). Then:
   - the session already runs in its own worktree: check out the branch there;
   - otherwise use the `EnterWorktree` tool if it is available, or `git worktree add` as in the
     reference doc, and run every later command inside that folder.

   Then `/rename claude/issue-<N>-<slug>`.

5. Implement, following the Plan and the repair comments, and the repo's `CLAUDE.md`. Add
   tests as the reference doc's "בדיקות" says: a test for every new parameter, endpoint, or bug
   fix, unless the repo's CLAUDE.md defines a manual check instead of a suite.

   **When the Plan has "עבודה במקביל", write the parts in parallel** (reference doc, "סעיף
   ה-Plan"; no such sub-heading: write it all here, in sequence):
   1. **Shared files first.** Write the shared files the contract depends on and commit them on
      the issue branch. Note that commit as `<start>`: every agent starts from it.
   2. **One agent per part, all in one message** so they run at the same time: the `Agent` tool
      with `isolation: "worktree"`, no cheaper `model` (quality stays the same). Each brief
      holds the full Plan, the contract, the part's path prefixes, `<start>`, and these rules:
      - first make sure the worktree sits on `<start>` (`git rev-parse HEAD`); if not,
        `git reset --hard <start>` (the worktree is new, so nothing is lost, and the commits
        stay on the agent's own branch);
      - install the part's dependencies, as the repo's `CLAUDE.md` says (a new worktree has
        none);
      - write only under the part's prefixes, and run only the part's tests;
      - a file outside the prefixes, or a change to the contract: stop and report, do not edit;
      - finish with one or more commits in the worktree, never a push; report the worktree
        path, the branch, and the files changed.
   3. **Check each part's files** against its prefixes:
      `git -C <agent worktree> diff --name-only <start>..HEAD`. A file outside them: look at it
      yourself before going on.
   4. **Join:** `git cherry-pick <start>..<agent branch>`, one part after the other. The parts
      share no file, so a conflict means something is wrong: `git cherry-pick --abort`, stop
      and report.
   5. **Check against the contract:** read both sides together, fix any mismatch, and finish
      what an agent stopped on. A change to the contract itself is a change to the plan
      (step 8).
   6. **Clean up:** `git worktree remove <agent worktree>` and `git branch -D <agent branch>`
      for each agent, only after its commits are on the issue branch. Then go on to step 6.

6. **Rebase onto the default branch before running the tests:**
   ```bash
   git fetch origin <default>
   git rebase origin/<default>
   ```
   Rebase, never merge. **If the rebase reports a conflict, stop:** `git rebase --abort`,
   leave the issue on `owner:claude`, comment with the conflicting files, open no PR.

7. Run the repo's checks, as "בדיקות" in the reference doc says: the commands from CLAUDE.md,
   plus any conditional suite whose area the diff touches
   (`git diff --name-only origin/<default>...HEAD`), or the manual check a suite-less repo
   defines.

   **A failure to run the tests is not permission to skip them.** If the install or the run
   fails, stop: leave the issue on `owner:claude`, comment with the exact error, open no PR.

8. If the plan turns out to be wrong mid-implementation, do not silently deviate. Update the
   Plan in the issue body (read it fresh first) and add a line to the plan log.

9. Open a PR against `<default>` whose body contains `Closes #<N>`. If a PR is already open
   from a previous round, push to it with `git push --force-with-lease` (step 6 rewrote the
   commits), never a plain `--force`. **Do not merge here.**

10. **While CI runs: review the diff and start the app.** Right after the push, note the
    pushed head as `<sha>` (`git rev-parse HEAD`): the review reads that commit, so a fix you
    make meanwhile does not move it. Then, in one message, so all three run at the same time:
    - **CI**, if the repo has checks: `gh pr checks <N> --watch --fail-fast`, in the background
      (`run_in_background`). No checks reported: say so.
    - **A review agent**: the `Agent` tool, no `isolation` (it reads this worktree) and no
      cheaper `model`. Its brief holds the full Plan, `<sha>`, the diff command
      `git diff origin/<default>...<sha>`, and pointers to the repo's `CLAUDE.md` and the rules
      in `~/.claude/rules/`. Its rules: read only; never edit a file or run a command that
      writes (commit, push, install, `gh issue edit`, `gh pr comment`); return a list of
      findings, each with file and line, a kind (bug / departs from the Plan / cleanup), and
      one sentence on why. On a repair round it reviews the whole diff of the PR.
    - **The app for review**, from the worktree, as the reference doc's "הרמה לסקירה" says:
      the command, ports and URL come from the repo's `CLAUDE.md`. Its outcome is one of: a
      link to the PR's app (started now, or already running from this branch), a link with a
      warning that names who holds the port, or a line saying why there is no link (the repo
      has no app, the session is not on Dolev's machine, the app failed to start). A failure
      here does not block the hand-off: say so in it.

    **When the agent returns**, check that `git status --porcelain` in the worktree is still
    empty (the agent wrote nothing), then decide each finding: right and inside the Plan: fix
    it. Wrong: note it with the reason. Right but outside the Plan: do not fix it; propose it
    as a task in the hand-off. Fixes are committed, the checks of step 7 run again, and the
    push starts a new CI run to wait for. **One review round only**: a fix is not reviewed
    again. The app runs from the worktree, so it picks the fix up; if its server does not
    reload on its own, restart it (reference doc, "עצירה", then "הסדר").

    **Red CI:** fix it in this run if the cause is clear, otherwise stay on `owner:claude` and
    report the failing job with a link. A red PR is never handed to Dolev for review. If there
    is no hand-off, stop the app and delete the registry file (reference doc, "עצירה"): there
    is nothing to review.

    Go on to step 11 only when CI is green on the last push and the agent has returned.

11. Hand off:
    ```bash
    gh issue edit <N> --add-label "status:in-review" --add-label "owner:<human>" \
                      --remove-label "status:ready-to-execute" --remove-label "owner:claude"
    # (or --remove-label "status:needs-repair" on a repair round)
    ```
    Then comment on the issue, in Hebrew, with what changed, what you tested, and anything Dolev
    should look at. On a repair round, say which of his points each change addresses. The
    comment has a "סקירת קוד" line: how many findings, which were fixed, and which were not and
    why. The app's outcome from step 10 goes into that comment and into the chat message, with
    one line on what to open in it.

12. **Keep the worktree until the merge**: the review app runs from it. If you entered it with
    `EnterWorktree`, leave it with `ExitWorktree` and keep it. The branch stays on the remote.

## Gate: not a Claude action

Dolev reviews the PR and, if it is good, sets `status:done` (or drags the card to Done). **That
alone is not permission to merge.** He asks for the merge explicitly.

## Part B: Merge

Only on Dolev's explicit request for that specific issue.

1. Find issues labelled `status:done` whose PR is still open.
2. Check that the PR still merges cleanly:
   ```bash
   gh pr view <N> --json mergeable,mergeStateStatus
   ```
   Anything other than `MERGEABLE`: rebase onto `origin/<default>` in a worktree, push with
   `--force-with-lease`, re-run the checks. If the rebase itself conflicts, stop and report.
3. Run the checks (step 7 of Part A). If they fail, stop and do not merge.
4. Check CI on the PR, waiting for a new run after a push (`gh pr checks <N> --watch
   --fail-fast`). Anything other than all green: stop, report the failing job with a link, do
   not merge. No checks reported at all: say so, and rely on step 3.
5. Squash-merge the PR. The issue closes through `Closes #<N>`. Check its open-questions
   section first; an unticked box is Dolev's call, not yours. `gh pr merge` pops an approval
   window for Dolev (an `ask` rule in `~/.claude/settings.json`): if he declines it, stop and
   report; never merge another way (such as `gh api`).
6. **Do not delete the remote branch.** The harness may block it; the repo's "Automatically
   delete head branches" setting handles it.
7. **Do delete the local branch**, which GitHub never touches. Stop its review app first, if
   one runs (reference doc, "הרמה לסקירה"), then remove its worktree, then
   delete it only if its tip is exactly the merged PR head (`git branch -d` always refuses after
   a squash merge, so this check replaces it):
   ```bash
   MERGED=$(gh pr view <N> --json state,headRefOid --jq 'select(.state=="MERGED") | .headRefOid')
   [ -n "$MERGED" ] && [ "$(git rev-parse <branch>)" = "$MERGED" ] && git branch -D <branch>
   ```
   Tips differ: leave the branch and say so in the summary.
8. Offer a session for the next issue, as the reference doc's "אחרי מיזוג: הצעה לסשן של
   המשימה הבאה" says: the next issue by `dev-next`'s rule, an opening prompt of `תחקור את
   #<N>` or `תקודד את #<N>`, and a fresh session unless all three conditions for a fork hold.
   Never start that issue in this session.

## Golden rules

- Never merge without Dolev's explicit go-ahead on that specific issue, whatever the label says.
- Never switch branches in the shared working copy; code is written in a worktree.
- Never start an issue without reading its sub-issues.
- If an issue lacks context, do not guess: comment with the question and flag it in the summary.
- Never touch an issue that does not carry `owner:claude`.
- One issue per run, and never a new one while three or more sit in `status:in-review` unless
  Dolev said yes to that.
- Never start an issue that has an open "Blocked by" link.
- A scan never reaches outside the current milestone; an issue Dolev named may. Never assign a
  milestone yourself.
- Never open a PR from a branch that has not just been rebased onto `origin/<default>`, or
  whose tests ran before that rebase; never hand off a red PR.
- Never attempt to delete branches. The one exception: the temporary local branches of the
  agents in step 5, once their commits are on the issue branch.
- An agent never pushes, and never writes outside the path prefixes the Plan gave its part.
