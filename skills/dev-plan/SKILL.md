---
name: dev-plan
description: Runs the Plan phase of Dolev's Claude-assisted GitHub pipeline in the current repo — reads issues labelled status:explore (new ones, and plans Dolev answered or sent back), researches feasibility, and writes a plan into the issue body. Use in any of Dolev's repos whenever he asks to run/process the Plan phase, to plan a specific issue ("תתכנן את #12"), or to check what is waiting for Claude to plan. Works in any repo that has the pipeline labels; if the repo has its own repo-specific plan skill, use that instead. Pairs with dev-code, which handles Execute and Merge.
---

# Plan phase

Part 1 of 2 of Dolev's GitHub × Claude Code pipeline (the other half is `dev-code`, covering
Execute + Merge). This phase reads issues, researches feasibility, and writes a plan: **no
feature code, and no branch switching in the working copy**.

## Step 0: Orient

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

- `repo_skills` lists a repo-specific plan skill? Use it instead.
- `ready` is `False`? Offer `dev-setup` and stop.
- Note `default_branch` (written `<default>` below) and `current_sprint`.

## Read first

In **`$HOME/.claude/skills/dev-setup/reference/`**: `pipeline.md` (the label vocabulary, the sprint), `issue-body.md` (how
to read the full context of an issue, the Plan format, body editing), `dependencies.md`,
`git-flow.md` (the working copy) and `ux.md` (the user-experience section). Everything mechanical lives there. Read them before step 1,
every run.

Then the repo's **`CLAUDE.md`**: where its requirements and decisions live, its working rules,
and its issue wording (headings, dependency line, Plan sub-headings) if it differs from the
standard template. The body headings come from the task and bug forms, read from where
`issue_forms` points (the repo, or `<owner>/.github`). An issue opened under older headings
keeps them: edit it in the headings it already has.

## Steps

1. Find the work. If Dolev named a specific issue, plan that one, even outside the current
   sprint (say so in the summary; never assign it a milestone). Otherwise, **inside the current
   sprint only**, by how much work waits on each issue:
   ```bash
   python "$HOME/.claude/skills/dev-setup/scripts/rank_issues.py" --status explore
   ```
   The first line names the sprint. An empty list means the sprint has nothing left to plan.
   Say so and stop; never reach outside the milestone. `BLOCKED by` does not skip a row here.

   **Up to three issues per run**: the top three rows. The fourth would be planned in a
   compacted context. The WIP gate applies to Execute, not here.

   `status:plan-questions` is Dolev's turn, never scanned here. When he answers, or sends a
   plan back, he moves the issue to `status:explore`, and this scan finds it like any other.
   When he answers in the chat with you, move it to `status:explore` yourself and go on.

2. For each issue, **read the whole thread first**: body, every comment, sub-issues, linked
   PR, and its "Blocked by" links. Read the blockers too, at least their goal and Plan: the
   plan you write builds on what they deliver. An open blocker does **not** stop planning. Two
   situations look alike but are not:
   - **a fresh issue**: no Plan content yet. Plan it from scratch.
   - **an issue with a Plan already**: Dolev answered or sent it back; revise the plan in place
     and add a line to the plan log saying what changed and why, citing where it came from: the
     comment, or Dolev's words in chat (quoted, with the date). An objection that arrived in chat
     is cited from chat; never post a comment just to have something to cite. The newest
     comment, or the chat, says which of two things arrived:
     - **Dolev answered your questions** (it came from `status:plan-questions`).
     - **Dolev read a plan at `status:waiting-approval` and sent it back** with an objection.
       Treat no part of the plan as settled. Address the objection itself.
     **Tick the questions he answered** in the open-questions section (`- [x]`, with the
     decision next to each). Never delete them. A question he did not address stays unticked.

3. Explore the relevant code against an up-to-date default branch, **without switching branches
   in the working copy** (`reference/git-flow.md`):
   ```bash
   git fetch origin <default>
   git show origin/<default>:path/to/file
   git grep <pattern> origin/<default> -- <path>
   ```
   If the session runs in its own worktree, or the working copy is clean, on `<default>` and
   not behind, reading files directly is fine. Follow the pointers in `CLAUDE.md` to the
   requirements sources for anything that is a requirements question rather than a code one,
   and check the open questions of the sprint umbrella and related issues before asking
   something that may already be recorded.

4. Create the branch **on the remote**, off `origin/<default>`, without a checkout. If the
   issue's Plan already names a branch, use that name:
   ```bash
   git push origin origin/<default>:refs/heads/claude/issue-<N>-<slug>
   ```
   Then `/rename claude/issue-<N>-<slug>` so the session is findable later.

5. Fill in the Plan section of the issue body, in the format from `reference/issue-body.md` and the
   heading level the repo's issues use. **Read the body fresh right before the edit**, keep the
   human-written sections byte-identical, write the file with LF line endings, then
   `gh issue edit <N> --body-file <file>` and verify.

   **Two levels, always: the decision, then the execution.** The plan opens with "בקצרה",
   written for Dolev's decision: the problem, what will change for the users, what is left out
   and which issue has it, and what waits for him. Business language only, no file or function
   names, at most 8 lines. Then "חוויית משתמש", also for the decision: the user, the flow, and
   what they see in each state, from the checklist in `reference/ux.md`. Every plan has it, except
   the short plan of a small task (step 7);
   work with nothing a user sees or touches gets one line saying so and why. Then "פירוט טכני"
   for the execution. No sections outside the format; a boundary with another issue is a line
   in "בקצרה", not a section of its own (`reference/issue-body.md`).
   An issue coming back for a revision whose plan predates this format gets it in the same edit.

   **The "בדיקות" sub-heading follows the table in `~/.claude/rules/code-tests.md`**: one line
   per change in the plan, with the kind of test its row requires, the cases, and the test file.

   **Can it be written in parallel?** When the work touches more than one layer (a backend and
   a frontend, say), check whether it splits into 2 to 3 parts with no file in common. If it
   does, write the "עבודה במקביל" sub-heading: the parts with their path prefixes, the shared
   files, and the contract between the parts (`reference/issue-body.md`). `dev-code` then
   writes the parts at the same time. If every file touches both sides, leave it out.

   **Check the scope before writing the plan.** Three questions, every issue:
   - **Too big?** If the issue holds more than one PR that can be reviewed on its own, propose a
     split in chat: each sub-issue's title, one line of scope, and the blockers between them.
     On Dolev's OK, split it with `dev-issue`, which holds the split rules; then plan the parts
     (they count toward the three per run). Size is the reason to split, not dependency: parts
     that depend on each other stay separate issues joined by "Blocked by".
   - **No work of its own?** An issue that is only a question or a decision for a single task,
     with no PR of its own, moves into that task: an unticked box in its open-questions section,
     or a line in its Plan. Then it is closed with a one-line pointer. A blocker that has work of
     its own stays a separate issue and stays a "Blocked by" link; blocking alone is never a
     reason to merge.
   - **Part of it belongs elsewhere?** Work an existing issue already owns is a line in "מה לא
     כלול, ואיפה כן", not part of this plan.

   A change to an issue whose status is not Claude's turn (`reference/pipeline.md`) is a step
   of this plan, made in Execute once Dolev approves.

   **Keep the dependencies true.** If exploration shows the issue needs something another issue
   delivers and no link says so, add the "Blocked by" link and the `#B` on the dependency line
   (both, in the same run). If a listed dependency is not needed, remove both and say why in the
   plan log. A business detail a person still owes is an open question, not a link. Where the
   plan assumes something about a blocker that has no plan yet, write the assumption down.

   **Content that belongs to another issue goes into that issue's body, never a comment.** A
   decision another task relies on is a line in its Plan section, for whoever plans it to build
   on; a question it must answer is an unticked box in its open-questions section. The
   human-written sections stay byte-identical. If that issue's status is not Claude's turn, the
   edit is a step of this plan, made in Execute once Dolev approves.

6. Set `area:*` if it is missing and the exploration made it obvious (only labels that exist).
   Likewise add `process` when the issue turns out to be work-management, rules or
   claude-config alignment work (the vocabulary table in `reference/pipeline.md`). Leave its milestone as it is.
   Add `costs-money` when the plan needs an expense (a paid cloud service, a paid API, a
   subscription) and say so in "בקצרה": the issue then waits on hold until Dolev approves.

7. Hand off, exactly one of three paths:

   **Small path**: the task meets all four conditions of "המסלול הקטן" in `reference/pipeline.md`
   (about 3 files at most; nothing a user sees, except a text fix; no deletion; no change to a
   contract or a new dependency). Any doubt: the normal path. The plan is the short plan from
   `reference/issue-body.md`, and the task goes straight to Execute, without Dolev's approval:
   ```bash
   gh label create "size:small" --color c5def5 --description "משימה קטנה: עוברת לביצוע בלי אישור תוכנית" 2>/dev/null || true
   gh issue edit <N> --add-label "size:small,status:ready-to-execute" --remove-label "status:explore"
   ```
   The label is created only when missing (without `--force`, so an existing description stays).
   A short plan back at `status:explore` without `size:small` is a task Dolev stopped: write the
   full plan and take the normal path. Never small-path it again.

   **Normal path**: the plan stands on its own:
   ```bash
   gh issue edit <N> --add-label "status:waiting-approval" --remove-label "status:explore"
   ```

   **Question path**: you would otherwise be guessing. Post the questions as a comment in
   Hebrew (numbered, each with the options you see and your recommendation, so Dolev can answer
   with a number), copy the same questions into the open-questions section as **unticked
   checkboxes**, and mark the blocked plan sections as pending. The comment is where Dolev
   reads; **the section is where the gate reads.** When Dolev is in the chat with you, ask the
   questions there too; his answer in chat counts like an answer in the issue.
   ```bash
   gh issue comment <N> --body-file <file>
   gh issue edit <N> --add-label "status:plan-questions" --remove-label "status:explore"
   ```

8. End the run with a summary in Hebrew: which issues moved to `status:waiting-approval` with
   their branch, and which moved to `status:plan-questions` and what was asked. Small-path
   issues get a line of their own, "עברו ישר לביצוע (קטנות)", each with its link and the reason
   it is small, so Dolev can stop one before code is written: he moves it to
   `status:explore` and removes `size:small`, and the next run writes the full plan. Confirm with
   `git status --short --branch` that the working copy is exactly as you found it.

## Golden rules

- Never write feature code in this phase, and never `git checkout` in the shared working copy.
- A dependency the plan relies on is a "Blocked by" link, not only a sentence in the plan.
- Never guess on an unclear issue; take the question path.
- The small path only when all four conditions hold; any doubt is the normal path.
- Never touch an issue whose status is not Claude's turn, unless Dolev named it.
- A comment is for questions only (the question path). A change Dolev asks for is an edit to
  the plan with a line in its log, and content for another issue is an edit to that issue.
- At most three issues per run.
- Split for size, link for dependency. An issue merges into another, on Dolev's OK, only when
  it has no PR of its own, or when two small issues overlap in files, neither has a PR yet,
  and together they are still one PR that can be reviewed on its own (`reference/dependencies.md`).
- A scan never reaches outside the current milestone; an issue Dolev named may. Never assign
  a milestone yourself.
- Never resolve an open question by picking the option that is easiest to implement. Ask,
  even when it costs a round trip.
