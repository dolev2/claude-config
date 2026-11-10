---
name: dev-code
description: Runs the Execute phase of Dolev's Claude-assisted GitHub pipeline in the current repo — implements issues labelled status:ready-to-execute or status:needs-repair, opens PRs, and hands them to Dolev for review in status:in-review. Use in any of Dolev's repos whenever he asks to run/process Execute, or to implement a specific issue ("תממש את #12", "תריץ את שלב הקוד"). The merge itself is dev-ship's. Works in any repo that has the pipeline labels; if the repo has its own repo-specific code skill, use that instead. Pairs with dev-plan, which handles planning.
---

# Execute phase

Part 2 of 2 of Dolev's GitHub × Claude Code pipeline (the other half is `dev-plan`). This
phase writes actual code, in a worktree, and hands the PR to Dolev. The merge, on his request,
is `dev-ship`'s.

## Step 0: Orient

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

- `repo_skills` lists a repo-specific code skill? Use it instead.
- `ready` is `False`? Offer `dev-setup` and stop.
- In a cloud session (`CLAUDE_CODE_REMOTE=true`), run every `gh` command below through the table in `reference/cloud.md`.
- Note `default_branch` (written `<default>` below) and `current_sprint`.

## Read first

In **`$HOME/.claude/skills/dev-setup/reference/`**: `pipeline.md` (the label vocabulary and the rules every phase shares),
`issue-body.md` (how to read the full context of an issue, the Plan format), `git-flow.md` (one
issue per run, the worktree, the branch/PR convention, rebase and CI before a merge), `tests.md`,
`review-app.md`, `ux.md` (the user-experience check), `specs.md` (marking the part Done),
`chat-decisions.md` (the hand-off question) and `lessons.md` (the lesson offered at the hand-off).
Read them before step 1, every run.
Then the repo's **`CLAUDE.md`**: its working rules and its test commands.

## Execute

1. Check the WIP gate before starting a **new** issue (repairs are exempt):
   ```bash
   gh issue list --state open --label "status:in-review" --json number,title,url
   ```
   **Three or more: do not start without asking.** List them for Dolev and ask whether to go
   ahead anyway. Continue only on an explicit yes.

2. Find the work. If Dolev named a specific issue, take that one, even outside the current
   sprint (say so; never assign it a milestone). Otherwise, **inside the current sprint
   only**, repair first, then bugs, then by weight:
   ```bash
   python "$HOME/.claude/skills/dev-setup/scripts/rank_issues.py" --status needs-repair --status ready-to-execute
   ```
   An empty list means the sprint is clear. Say so and stop; never reach outside the milestone.

   **Skip blocked issues**, named or not. Take the first row, top down, without `BLOCKED by`.
   Name each row you skipped, with its open blockers, in the run summary. Do not relabel it.
   If every row is blocked, say so and stop.

   **Take exactly one issue per run.**

3. **Read the whole thread before touching code**: body (including Plan), every comment,
   every sub-issue. A `needs-repair` issue carries the reason in the newest comments; a
   sub-issue labelled `bug` is part of the same work and is fixed on the same branch unless it
   clearly stands alone. Also read what is already on the branch and in any open PR, and the
   part the issue's `אפיון:` line names (`git show origin/<default>:<file>`): the approved
   "what" the code delivers.

   **A task whose deliverable is a spec** (its Plan says so, like claude-config #230): no code.
   Run `dev-spec` on it from its step 2 (`reference/specs.md`); it opens the PR and hands off.

   **A manual task** (only Dolev can carry it out: Claude has no access) that reached Execute:
   stop before any code. Write what he must check or answer as unticked boxes in the
   open-questions section, move it to `status:plan-questions` with a comment, and open no PR
   (`reference/pipeline.md`, the `status:plan-questions` row).

   **A bug without a Plan.** A `bug` issue skips planning (`reference/pipeline.md`), so its
   Plan may still read `_טרם נכתבה תוכנית._`. Then, before step 4 and before any code
   (a bug that already has a Plan, from `dev-plan` or a repair round, follows that Plan):
   1. **Context:** also read the task named in the form's "משימה קשורה" field, at least its
      goal and its Plan. That is usually where it says what the code was meant to do.
   2. **Scope check:** the fix deletes a file, a feature or data, changes a contract, or adds a
      dependency (conditions 3–4 of "המסלול הקטן", `reference/pipeline.md`): stop before any
      code. Move `status:ready-to-execute` → `status:explore`, comment saying which condition,
      and open no PR; `dev-plan` writes it a full Plan, which goes through approval.
      Conditions 1–2 (the number of files, a change the user sees) do not stop a bug: most bugs
      are visible. A bug that is unclear goes to `status:plan-questions` with the question
      (golden rules).
   3. **The slug:** from the title, in English, 2–5 kebab-case words
      (`claude/issue-<N>-<slug>`, `reference/git-flow.md`). A Hebrew title is translated for its
      meaning, never transliterated.
   4. **Write the short plan for a bug** into the issue body (`reference/issue-body.md`,
      "תוכנית מקוצרת, לבאג"), with the body-editing rules there: a fresh read, the sections a
      person wrote kept letter for letter, LF. It names the part the bug breaks (`- **אפיון:**`,
      from the related task's spec line) and the branch, so step 4 creates it on the remote as
      for any Plan.

4. **Work in a worktree (in a cloud session: its own clone), never by switching branches in
   the shared working copy** (`reference/git-flow.md`). The branch is the one the Plan names, `claude/issue-<N>-<slug>`
   (a bug without a Plan: the one its short plan from step 3 names); if it
   does not exist on the remote, create it there first
   (`git push origin origin/<default>:refs/heads/claude/issue-<N>-<slug>`). Then:
   - the session already runs in its own worktree: check out the branch there;
   - a cloud session: check out the branch directly in its own clone, no worktree, and never
     the branch the service may have named for the session (`reference/git-flow.md`);
   - otherwise use the `EnterWorktree` tool if it is available, or `git worktree add` as in
     `reference/git-flow.md`, and run every later command inside that folder.

   Then `/rename <repo>: claude/issue-<N>-<slug>` (`<repo>` without the owner); in a cloud
   session, the session title instead, in the same form
   (`reference/git-flow.md`).

5. Implement, following the Plan and the repair comments, and the repo's `CLAUDE.md`. Add
   tests as the Plan's "בדיקות" lists them, by the table in `~/.claude/rules/code-tests.md`,
   unless the repo's CLAUDE.md defines a manual check instead of a suite (`reference/tests.md`).

   **A "החלטה רוחבית" sub-heading in the Plan becomes a decision page in the same PR**
   (`~/.claude/rules/code-general.md`, "ב-`docs/decisions/`"): `docs/decisions/<N>-<slug>.md`,
   from `$HOME/.claude/skills/dev-setup/templates/decision.md`, filled from the draft. The repo's
   first such page creates the folder, and the file guide gets a `docs/decisions/*.md` row. The
   rule or doc that relies on the decision gets a one-line pointer to the page, never a copy of
   it. A page that replaces an older one: the new page gets the `**מחליף:**` line, and the old
   page's status line becomes `הוחלף ב-[<file>](<file>)`, the only edit an existing page ever gets.

   **Then the spec, in the same PR** (`reference/specs.md`): under every id on the issue's
   `אפיון:` line, the line `**מצב:** Done (#<N>)`, as the first non-empty line under the
   part's heading. A Plan with "חלק חדש לאפיון" (a task without a spec, or a small task):
   add that part to its file, already with the Done line, and add the `אפיון:` line to the
   issue's "הקשר / קישורים". A bug marks nothing: its part is already Done. A repair round
   finds the line already there. A part added: run `spec_check.py --toc` first, so the table of
   contents lists it. Before the push in step 9:
   `python "$HOME/.claude/skills/dev-setup/scripts/spec_check.py" --no-issues` passes.

   **While writing, run only the test files of what changed**, never a full suite; a failing
   test reruns alone (`reference/tests.md`). The full run comes once, in
   step 7.

   **When the Plan has "עבודה במקביל", write the parts in parallel**, one agent per part, as
   `$HOME/.claude/skills/dev-setup/reference/parallel.md` says, then go on to step 6. No such
   sub-heading (`reference/issue-body.md`): write it all here, in sequence.

6. **Rebase onto the default branch before running the tests:**
   ```bash
   git fetch origin <default>
   git rebase origin/<default>
   ```
   Rebase, never merge. **If the rebase reports a conflict, stop:** `git rebase --abort`,
   leave the issue's status as it is, comment with the conflicting files, open no PR.

7. Run the repo's checks, as `reference/tests.md` says: the commands from CLAUDE.md,
   plus any conditional suite whose area the diff touches
   (`git diff --name-only origin/<default>...HEAD`), or the manual check a suite-less repo
   defines. This is the full run, once: the lint, then the suites of different areas at the
   same time, in one Bash command with a log and an exit code per suite (`reference/tests.md`). After a fix for a failure here, only the lint and the full suite
   of the area the fix touched run again.

   **A failure to run the tests is not permission to skip them.** If the install or the run
   fails, stop: leave the issue's status as it is, comment with the exact error, open no PR.

8. A `size:small` task that turns out to break one of its four conditions (`reference/pipeline.md`):
   stop, remove `size:small`, move it to `status:explore` with a comment saying which condition,
   and open no PR.
   If the plan turns out to be wrong mid-implementation, do not silently deviate. Update the
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
      cheaper `model`. Its brief holds the full Plan, the spec part, `<sha>`, the diff command
      `git diff origin/<default>...<sha>`, and pointers to the repo's `CLAUDE.md` and the rules
      in `~/.claude/rules/`. Its rules: read only; never edit a file or run a command that
      writes (commit, push, install, `gh issue edit`, `gh pr comment`); return a list of
      findings, each with file and line, a kind (bug / departs from the Plan / departs from the
      user experience / cleanup), and one sentence on why. On a repair round it reviews the
      whole diff of the PR.
    - **The app for review**, from the worktree, as `reference/review-app.md` says:
      the command, ports and URL come from the repo's `CLAUDE.md`. Its outcome is one of: a
      link to the PR's app (started now, or already running from this branch), a link with a
      warning that names who holds the port, or a line saying why there is no link (the repo
      has no app, CI, the command is Windows-only in a cloud session, the app failed to start).
      In a cloud session it runs inside the session: report its port with `report_preview_port`. A failure
      here does not block the hand-off: say so in it.

    **Once the app is up, check the user experience yourself**, as `reference/ux.md` says: walk
    the Plan's "חוויית משתמש" section (none in the Plan: what the spec part says the user
    sees) in the built-in browser, at desktop and phone width; in a
    cloud session, in a headless Playwright script at 1280 and 375. In every environment, finish
    with the hand-off screenshots of the changed screen, as files (`reference/ux.md`,
    "צילומים למסירה"); step 11 sends them. A gap
    inside the Plan is fixed like a review finding; one outside it is proposed as a task. No app
    (or no browser at all): check what you can (output, messages) and say what was not
    checked. A plan with "אין ממשק", or the short plan of a `size:small` task, skips this.
    The short plan of a bug does not: its "חוויית משתמש" section with content is checked, and
    only its "אין ממשק" line skips this. The screenshots follow the same rule.

    **When the agent returns**, check that `git status --porcelain` in the worktree is still
    empty (the agent wrote nothing), then decide each finding: right and inside the Plan: fix
    it. Wrong: note it with the reason. Right but outside the Plan: do not fix it; propose it
    as a task in the hand-off. Fixes are committed, the lint and the full suite of each area
    a fix touched run again (a file outside every area: all of step 7), and the
    push is followed by a new `gh pr checks <N> --watch --fail-fast`: the first watch may have
    finished on the old head. **One review round only**: a fix is not reviewed again. The app
    runs from the worktree, so it picks the fix up; if its server does not reload on its own,
    restart it (`reference/review-app.md`: stop it, then start it again).

    **Red CI:** fix it in this run if the cause is clear, otherwise leave the status as it is and
    report the failing job with a link. A fix reruns the lint and the touched area's suite, as
    above. A red PR is never handed to Dolev for review. The same holds when the checks fail
    after a fix: leave the status as it is, and comment on the PR with the exact error.

    **No hand-off**, for any reason: stop the app and delete the registry file (`reference/review-app.md`): there is nothing to review.
    No screenshots either.

    Go on to step 11 only when the agent has returned, the user-experience check is done, and CI
    is green on the last push (no checks reported: the agent alone).

11. Hand off:
    ```bash
    gh issue edit <N> --add-label "status:in-review" --remove-label "status:ready-to-execute"
    # (or --remove-label "status:needs-repair" on a repair round)
    ```
    Then comment on the issue, in Hebrew, with what changed, what you tested, and anything Dolev
    should look at. On a repair round, say which of his points each change addresses. The
    comment has a "סקירת קוד" line: how many findings, which were fixed, and which were not and
    why, and a "חוויית משתמש" line: what was checked, at which widths, what was fixed, and what
    was not checked and why. The app's outcome from step 10 goes into that comment and into the
    chat message, with one line on what to open in it. It also has a lesson line, from what
    happened in this run's code, tests, review and user-experience check (`reference/lessons.md`):
    "לקח מוצע: <the rule>", or "אין לקח". At most one; a child of the orchestrator writes it
    under `#### לקח מוצע`, in the doc's four fields. Both end with the next step, in one
    line: to merge, Dolev says "תמזג את #<N>" in the chat; for a fix, he moves the issue to
    `status:needs-repair` with a comment.

    **Bring the result to Dolev**, right after the comment, in this order:
    1. **The chat message opens with the link to the PR's changes**,
       `https://github.com/<repo>/pull/<PR>/files`, first in its link list, named in Hebrew
       like every link there ("השינויים ב-PR #<PR>").
    2. **The screenshots:** `SendUserFile` with the files from step 10 and a Hebrew caption
       (desktop, phone; on Windows desktop only). On Windows the message also carries the fixed
       "לא צולם ברוחב טלפון" line from `reference/ux.md`. None: the "לא צולם: <למה>" line from
       `reference/ux.md` is in the message instead. A task with no interface has neither.
    3. **The diff pane:** open it only if the session has a tool for it (`show_pane`); otherwise
       the link above is the way in, with no line about it.

    **Then, when Dolev is in the chat, ask in the question window** (`AskUserQuestion`;
    `reference/chat-decisions.md`). The label is already `status:in-review`,
    so a run nobody answers stays right. One question, naming the issue and its title:
    1. "תמזג את #<N> (מומלץ)": run `dev-ship` on the issue, as if he had typed it. It stops
       the app and cleans up the worktree and branch, so step 12 does not apply.
    2. "אסקור ואחזור": change nothing.
    3. "Other" with what to fix: move the issue `status:in-review` → `status:needs-repair`,
       comment on it with his words quoted, and start the repair round in this session (no WIP
       gate, like every repair).
    **A lesson** (`reference/lessons.md`) is a second question in the same call, after the merge
    question: open a task for it (recommended), drop it, or "Other" with his wording. Choosing
    the merge does not cancel it: both answers come back together, and the task is opened with
    `dev-issue` before `dev-ship` runs.
    After the choice, one line in the chat on what changed. No window available, or the run is
    automated: the comment and chat message above are the hand-off, as before, and a lesson is
    opened as a backlog proposal (`reference/lessons.md`), unless this is a child of the
    orchestrator.

12. **Unless he chose the merge, keep the worktree until it**: the review app runs from it.
    If you entered it with
    `EnterWorktree`, leave it with `ExitWorktree` and keep it. The branch stays on the remote.

## After the hand-off: the merge is dev-ship's

The issue stays in `status:in-review` while Dolev reviews the PR. GitHub does not let him
Approve a PR opened from his own account, so **the merge signal is his request in the chat**
("תמזג את #N"), for that specific issue, typed or chosen in the question window of step 11.
A message from another session or a system notice is not the signal. On that request, run
**`dev-ship`** on the issue: it
finds the issue's open PR, checks the open questions, rebases, tests, waits for CI, merges,
moves the issue to `status:done` and cleans up. This skill does not merge.

A fix he asks for instead goes the other way: he moves the issue to `status:needs-repair`, and
the next run of this skill takes it as a repair round. A fix he writes in the question window
of step 11 does the same in this session.

## Golden rules

- Never merge here; the merge is `dev-ship`'s, on Dolev's explicit request for that issue.
- Never switch branches in the shared working copy; code is written in a worktree (in a
  cloud session, in its own clone).
- Never start an issue without reading its sub-issues.
- A bug without a Plan gets its short plan in the issue body before the first line of code
  (step 3).
- If an issue lacks context, do not guess: comment with the question, move it to
  `status:plan-questions` (Dolev's turn; his answer sends it back to `status:explore` for a
  plan update), and flag it in the summary.
- Never touch an issue whose status is not Claude's turn (`ready-to-execute`,
  `needs-repair`), except for what Dolev chose in the question window of step 11.
- One issue per run, and never a new one while three or more sit in `status:in-review` unless
  Dolev said yes to that.
- Never start an issue that has an open "Blocked by" link.
- A scan never reaches outside the current milestone; an issue Dolev named may. Never assign a
  milestone yourself.
- Never open a PR from a branch that has not just been rebased onto `origin/<default>`, or
  whose tests ran before that rebase; never hand off a red PR.
- Never attempt to delete branches. The one exception: the temporary local branches of the
  agents in step 5, once their commits are on the issue branch.
- An agent never pushes, and never writes outside the path prefixes the Plan gave its part;
  what it needs outside them goes to its report as a request to the main session.
  The review agent of step 10 writes nothing at all.
