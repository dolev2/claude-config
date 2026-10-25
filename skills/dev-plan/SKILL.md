---
name: dev-plan
description: Runs the Plan phase of Dolev's Claude-assisted GitHub pipeline in the current repo — reads issues labelled owner:claude + status:explore (and plan-questions handed back), researches feasibility, and writes a plan into the issue body. Use in any of Dolev's repos whenever he asks to run/process the Plan phase, to plan a specific issue ("תתכנן את #12"), or to check what is waiting for Claude to plan. Works in any repo that has the pipeline labels; if the repo has its own repo-specific plan skill, use that instead. Pairs with dev-code, which handles Execute and Merge.
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
- Note `default_branch` (written `<default>` below), `human` (`owner:<human>`),
  `sync_marker`, and `current_sprint`.

## Read first

**`$HOME/.claude/skills/dev-setup/reference/pipeline.md`**: the label vocabulary, how to read
the full context of an issue, the Plan format, body editing, and the section "עותק העבודה".
Everything mechanical lives there. Read it before step 1, every run.

Then the repo's **`CLAUDE.md`**: where its requirements and decisions live, its working rules,
and its issue wording (headings, dependency line, Plan sub-headings) if it differs from the
standard template. The body headings come from the task and bug forms, read from where
`issue_forms` points (the repo, or `<owner>/.github`). An issue opened under older headings
keeps them: edit it in the headings it already has.

## Steps

1. Find the work. If Dolev named a specific issue, plan that one, even outside the current
   sprint (say so in the summary; never assign it a milestone). Otherwise, **inside the current
   sprint only**, answered questions first, then by how much work waits on each issue:
   ```bash
   python "$HOME/.claude/skills/dev-setup/scripts/rank_issues.py" --owner claude --status plan-questions --status explore
   ```
   The first line names the sprint. An empty list means the sprint has nothing left to plan.
   Say so and stop; never reach outside the milestone. `BLOCKED by` does not skip a row here.

   **Up to three issues per run**: the top three rows. The fourth would be planned in a
   compacted context. The WIP gate applies to Execute, not here.

   **Do not drop `--status plan-questions`.** `status:plan-questions` + `owner:claude` is the
   state an issue lands in the moment Dolev answers, and this is the only phase that claims it.

2. For each issue, **read the whole thread first**: body, every comment, sub-issues, linked
   PR, and its "Blocked by" links. Read the blockers too, at least their goal and Plan: the
   plan you write builds on what they deliver. An open blocker does **not** stop planning. Two
   situations look alike but are not:
   - **a fresh issue**: no Plan content yet. Plan it from scratch.
   - **an issue coming back from `status:plan-questions`**: the plan exists; revise it in place
     and add a line to the plan log saying what changed and why, citing the comment. The newest
     comment says which of two things arrived:
     - **Dolev answered your questions** and flipped `owner` back to Claude.
     - **Dolev read a plan at `status:waiting-approval` and sent it back** with an objection.
       Treat no part of the plan as settled. Address the objection itself.
     **Tick the questions he answered** in the open-questions section (`- [x]`, with the
     decision next to each). Never delete them. A question he did not address stays unticked.

3. Explore the relevant code against an up-to-date default branch, **without switching branches
   in the working copy** (reference doc, "עותק העבודה"):
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

5. Fill in the Plan section of the issue body, in the format from the reference doc and the
   heading level the repo's issues use. **Read the body fresh right before the edit**, keep the
   human-written sections byte-identical, write the file with LF line endings, preserve the
   hidden sync marker unchanged, then `gh issue edit <N> --body-file <file>` and verify.

   **Two levels, always.** The plan opens with "בקצרה", written for Dolev's decision: the
   problem, what will change for the users, what is left out and which issue has it, and what
   waits for him. Business language only, no file or function names, at most 8 lines. Then
   "פירוט טכני" for the execution. No sections outside the format; a boundary with another
   issue is a line in "בקצרה", not a section of its own (reference doc, "סעיף ה-Plan").
   An issue coming back for a revision whose plan predates this format gets it in the same edit.

   **Keep the dependencies true.** If exploration shows the issue needs something another issue
   delivers and no link says so, add the "Blocked by" link and the `#B` on the dependency line
   (both, in the same run). If a listed dependency is not needed, remove both and say why in the
   plan log. A business detail a person still owes is an open question, not a link. Where the
   plan assumes something about a blocker that has no plan yet, write the assumption down.

6. Set `area:*` if it is missing and the exploration made it obvious (only labels that exist).

7. Hand off, exactly one of two paths:

   **Normal path**: the plan stands on its own:
   ```bash
   gh issue edit <N> --add-label "status:waiting-approval" --add-label "owner:<human>" \
                     --remove-label "status:explore" --remove-label "owner:claude"
   ```
   (From `plan-questions`, remove `status:plan-questions` instead.)

   **Question path**: you would otherwise be guessing. Post the questions as a comment in
   Hebrew (numbered, each with the options you see and your recommendation, so Dolev can answer
   with a number), copy the same questions into the open-questions section as **unticked
   checkboxes**, and mark the blocked plan sections as pending. The comment is where Dolev
   reads; **the section is where the gate reads.**
   ```bash
   gh issue comment <N> --body-file <file>
   gh issue edit <N> --add-label "status:plan-questions" --add-label "owner:<human>" \
                     --remove-label "status:explore" --remove-label "owner:claude"
   ```

8. End the run with a summary in Hebrew: which issues moved to `status:waiting-approval` with
   their branch, and which moved to `status:plan-questions` and what was asked. Confirm with
   `git status --short --branch` that the working copy is exactly as you found it.

## Golden rules

- Never write feature code in this phase, and never `git checkout` in the shared working copy.
- A dependency the plan relies on is a "Blocked by" link, not only a sentence in the plan.
- Never guess on an unclear issue; take the question path.
- Never touch an issue that does not carry `owner:claude`.
- At most three issues per run.
- A scan never reaches outside the current milestone; an issue Dolev named may. Never assign
  a milestone yourself.
- Never resolve an open question by picking the option that is easiest to implement. Ask,
  even when it costs a round trip.
