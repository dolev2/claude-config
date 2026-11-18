---
name: dev-plan
description: Runs the Plan phase of Dolev's Claude-assisted GitHub pipeline in the current repo — reads issues labelled status:explore (new ones, and plans Dolev answered), researches feasibility, writes a plan into the issue body, and starts the code at once (dev-code) when the plan has no open question. Use in any of Dolev's repos whenever he asks to run/process the Plan phase, to plan a specific issue ("תתכנן את #12"), or to check what is waiting for Claude to plan. Works in any repo that has the pipeline labels; if the repo has its own repo-specific plan skill, use that instead. Pairs with dev-code, which handles Execute; dev-ship merges.
---

# Plan phase

Part 1 of 2 of Dolev's GitHub × Claude Code pipeline (the other half is `dev-code`, covering
Execute, up to a PR in review; `dev-ship` merges). This phase reads issues, researches feasibility, and writes a plan: **no
feature code, and no branch switching in the working copy**. The plan is not a gate (S-1.64,
`reference/pipeline.md`): a plan with no open question goes straight to `dev-code`, in this
session (step 8).

## Step 0: Orient

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

- `repo_skills` lists a repo-specific plan skill? Use it instead.
- `ready` is `False`? Offer `dev-setup` and stop.
- In a cloud session (`CLAUDE_CODE_REMOTE=true`), run every `gh` command below through the table in `reference/cloud.md`.
- Note `default_branch` (written `<default>` below) and `current_sprint`.

## Read first

In **`$HOME/.claude/skills/dev-setup/reference/`**: `pipeline.md` (the label vocabulary, the sprint), `issue-body.md` (how
to read the full context of an issue, the Plan format, body editing), `specs.md` (the spec
stage: the part an issue implements, the short Plan, the gate for an issue without a spec), `dependencies.md`,
`git-flow.md` (the working copy), `ux.md` (the user-experience section) and `chat-decisions.md`
(asking Dolev in the question window). Everything mechanical lives there. Read them before step 1,
every run.

Then the repo's **`CLAUDE.md`**: where its requirements and decisions live, its working rules,
and its issue wording (headings, dependency line, Plan sub-headings) if it differs from the
standard template. The body headings come from the task and bug forms, read from where
`issue_forms` points (the repo, or `<owner>/.github`). An issue opened under older headings
keeps them: edit it in the headings it already has.

## Steps

1. Find the work. If Dolev named a specific issue, plan that one, even outside the current
   sprint (say so in the summary); a named issue labelled `paused` is asked about first (below). Otherwise, **inside the current sprint only**, in the
   sprint order (`reference/dependencies.md`; the sprint scope: `reference/pipeline.md`):
   ```bash
   python "$HOME/.claude/skills/dev-setup/scripts/rank_issues.py" --status explore
   ```
   The first line names the sprint. An empty list means the sprint has nothing left to plan.
   Say so and stop.

   **A named issue labelled `paused`:** before anything else here, even the blocked check,
   ask the question of `reference/chat-decisions.md` ("משימה מושהית שדולב ביקש במספר";
   the reason: `pause_reason.py <N>`), unless it was already asked for this request (rule 5
   there: `dev-next` asked).
   "לא להתחיל": the chat line of rule 4 there, and stop. No window: write the question and
   stop (rule 6 there).

   **Skip blocked issues** (`reference/dependencies.md`, claude-config #253): a decision in a
   blocker can change the file layout and leave a plan stale. Take rows top down, without
   `BLOCKED by`, and name each row you skipped, with its open blockers, in the summary. Do not
   relabel it. If every row is blocked, say so and stop. An issue Dolev named that is blocked:
   say it is blocked and by what, and plan it only when he explicitly asks for that.

   **Up to three issues per run**: the top three unblocked rows. The fourth would be planned in a
   compacted context. The WIP gate applies to Execute, not here.

   `status:plan-questions` is Dolev's turn, never scanned here. When he answers, he moves the
   issue to `status:explore`, and this scan finds it like any other.
   When he answers in the chat with you, move it to `status:explore` yourself and go on.

2. For each issue, **read the whole thread first**: body, every comment, sub-issues, linked
   PR, and its "Blocked by" links. Read the blockers too, at least their goal and Plan: the
   plan you write builds on what they deliver. **Read the issue's part in the spec**: the
   `אפיון:` line in "הקשר / קישורים" names the file and the ids (`issue_body.spec_line` reads
   it), and the part itself comes from `git show origin/<default>:<file>`. That part is the
   approved "what" and "why"; the plan is the "how".

   **The gate: no open part, no plan** (`reference/specs.md`, "issue בלי אפיון"; claude-config
   #243). Before any code is read: an issue that is not a bug, and whose `אפיון:` line is
   missing or names a part that is already Done, gets no plan and no branch. Move it
   `status:explore` → `status:backlog` and comment: it has no open part in the spec, so it goes
   back to the backlog as a proposal (a Done part: the change is first a change to that part).
   Its milestone stays, since it is Dolev's, and the comment says so, with what comes next by
   that milestone (`reference/specs.md`, "issue בלי אפיון", item 2):
   - **the current sprint's milestone** (`current_sprint` of step 0): it is now an approved
     proposal, so the orchestrator writes its spec in its next check (S-2.14); whoever does not
     want that removes the milestone;
   - **no milestone, or another one:** "תכתוב אפיון ל-#N", as before.
   It
   does not count toward the three issues of the run, and it is none of the two hand-off
   paths of step 7: the summary gives it a line of its own (step 8).

   Two situations look alike but are not:
   - **a fresh issue**: no Plan content yet. Plan it from scratch.
   - **an issue with a Plan already**: Dolev answered, or the spec changed; revise the plan in place
     and add a line to the plan log saying what changed and why, citing where it came from: the
     comment, or Dolev's words in chat (quoted, with the date). An objection that arrived in chat
     is cited from chat; never post a comment just to have something to cite. The newest
     comment, or the chat, says which of two things arrived:
     - **Dolev answered your questions** (it came from `status:plan-questions`).
     - **The part it builds changed in the spec** (`dev-issue`, "עדכון אחרי שינוי באפיון";
       claude-config #244): the newest comment says so and links the spec PR. Read the part
       again from `origin/<default>`, treat no part of the plan as settled, and cite that PR in
       the plan log line.
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

   **A blocker found here stops this issue before step 4.** Exploration shows the issue needs
   something an issue still open delivers, and no link says so: add the "Blocked by" link and
   the `#B` on the dependency line now (step 5, "Keep the dependencies true"), then stop. No
   branch, no Plan, the status stays as it is, and the summary names it with that blocker, as
   in step 1. The one exception is the one of step 1: Dolev named the issue and explicitly
   asked to plan it anyway.

4. Create the branch **on the remote**, off `origin/<default>`, without a checkout. If the
   issue's Plan already names a branch, use that name:
   ```bash
   git push origin origin/<default>:refs/heads/claude/issue-<N>-<slug>
   ```
   Then `/rename <repo>: claude/issue-<N>-<slug>` (`<repo>` without the owner) so the session
   is findable later. In a cloud session `/rename` is unavailable: set the title instead, in the same form (`reference/git-flow.md`).

5. Fill in the Plan section of the issue body, in the format from `reference/issue-body.md` and the
   heading level the repo's issues use. **Read the body fresh right before the edit**, keep the
   human-written sections byte-identical, write the file with LF line endings, then
   `gh issue edit <N> --body-file <file>` and verify.

   **An issue with a spec line gets the short Plan** (`reference/issue-body.md`): "בקצרה" in three
   lines, `- **אפיון:**` with the file, the id and the part's name, `- **איפה באפיון:**`, and
   "החלטות שמחכות לדולב"; then "פירוט טכני" as below. No "חוויית משתמש": the part holds it,
   and `dev-code` checks against it there.

   **The full plan below is only for a bug back in planning**: `dev-code` sends a bug that
   deletes something or changes a contract to `status:explore` (`reference/specs.md`, "issue
   בלי אפיון"). A task without an open part never gets here: the gate of step 2 sent it back.

   **The full plan has two levels: the decision, then the execution.** It opens with "בקצרה",
   written for Dolev's decision: the problem, what will change for the users, what is left out
   and which issue has it, where the task sits in the spec, and what waits for him. Business language only, no file or function
   names, at most 8 lines. Then "חוויית משתמש", also for the decision: the user, the flow, and
   what they see in each state, from the checklist in `reference/ux.md`. Every full plan has it
   (not the short Plan of an issue with a spec line);
   work with nothing a user sees or touches gets one line saying so and why. Then "פירוט טכני"
   for the execution. No sections outside the format; a boundary with another issue is a line
   in "בקצרה", not a section of its own (`reference/issue-body.md`).
   An issue coming back for a revision whose plan predates this format gets it in the same edit.

   **Every plan tells Dolev where the task sits in the spec**: the line
   `- **איפה באפיון:**`, right under `- **אפיון:**`; in the full plan of a bug, it comes before
   "החלטות שמחכות לדולב" and names the Done part the bug breaks. Three to five
   sentences that tell the change as a short story in its context, in business language, not a
   list and not a dry summary: the chapter and the group the part sits in and what the chapter
   does, what problem the part solves and why it matters, and what comes before or after it, when
   there is any (the spec's "תלוי ב-S-x.y" lines and the issue's Blocked by). One sentence per
   line, each ending with `\`; they do not count toward the 8-line limit. The short plan of a bug (written by `dev-code`) does not: it points at a Done part
   it breaks (`reference/issue-body.md`).

   **The "בדיקות" sub-heading follows the table in `~/.claude/rules/code-tests.md`**: one line
   per change in the plan, with the kind of test its row requires, the cases, and the test file.

   **Can it be written in parallel?** When the work touches more than one layer (a backend and
   a frontend, say), check whether it splits into 2 to 3 parts with no file in common. If it
   does, write the "עבודה במקביל" sub-heading: the parts with their path prefixes, the shared
   files, and the contract between the parts (`reference/issue-body.md`). `dev-code` then
   writes the parts at the same time. If every file touches both sides, leave it out.

   **Does it decide something other tasks will follow?** A tool, an architecture or a work
   rule that outlives this task (`~/.claude/rules/code-general.md`, "ב-`docs/decisions/`"):
   write the "החלטה רוחבית" sub-heading, the draft of its decision page
   (`reference/issue-body.md`). Dolev approves it in the review of the PR; `dev-code` writes the
   page in the same PR. If it replaces an existing page in `docs/decisions/`, name that page. A choice
   that holds for this task alone stays in "הגישה".

   **Check the scope before writing the plan.** These questions, every issue:
   - **Wider than its part?** The request goes beyond the part on the spec line (another screen,
     another rule): propose to Dolev to update the spec first, through `dev-spec`, and do not
     widen the plan past the part. The code does not start: the proposal is the open question
     of the question path (step 7), so the issue waits for Dolev at `status:plan-questions`.
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
   - **Nothing Claude can do?** A task only Dolev can carry out (Claude has no access, like the
     Netlify check of #75) takes the question route: what he must check or answer goes in as
     unticked boxes in the open-questions section, and the issue moves to
     `status:plan-questions` (`reference/pipeline.md`, the `status:plan-questions` row). His answer sends it back
     to `status:explore`, and the plan goes on from there.

   A change to an issue whose status is not Claude's turn (`reference/pipeline.md`) is a step
   of this plan, made in Execute.

   **Keep the dependencies true.** If exploration shows the issue needs something another issue
   delivers and no link says so, add the "Blocked by" link and the `#B` on the dependency line
   (both, in the same run). If a listed dependency is not needed, remove both and say why in the
   plan log. A business detail a person still owes is an open question, not a link. A new link
   to a blocker that is still open was already found in step 3, which stopped there. When Dolev
   explicitly asked to plan a blocked issue, write down what the plan assumes about a blocker
   that has no plan yet.

   **Content that belongs to another issue goes into that issue's body, never a comment.** A
   decision another task relies on is a line in its Plan section, for whoever plans it to build
   on; a question it must answer is an unticked box in its open-questions section. The
   human-written sections stay byte-identical. If that issue's status is not Claude's turn, the
   edit is a step of this plan, made in Execute.

6. Set `area:*` if it is missing and the exploration made it obvious (only labels that exist).
   Likewise add `process` when the issue turns out to be work-management, rules or
   claude-config alignment work (the vocabulary table in `reference/pipeline.md`). Leave its milestone as it is.
   Add `costs-money` when the plan needs an expense, and say in "בקצרה" that the expense waits
   for Dolev (what the label does and who lifts it: `reference/pipeline.md`). That is an
   approval of the expense, not of the plan.

7. Hand off, exactly one of two paths:

   **Ready path**: the plan stands on its own, with no open question:
   ```bash
   gh issue edit <N> --add-label "status:ready-to-execute" --remove-label "status:explore"
   ```
   The code itself starts in step 8, with its line in the chat.

   **Question path**: you would otherwise be guessing. Post the questions as a comment in
   Hebrew (numbered, each with the options you see and your recommendation, so Dolev can answer
   with a number), copy the same questions into the open-questions section as **unticked
   checkboxes**, and mark the blocked plan sections as pending. The comment is where Dolev
   reads; **the section is where the gate reads.**
   ```bash
   gh issue comment <N> --body-file <file>
   gh issue edit <N> --add-label "status:plan-questions" --remove-label "status:explore"
   ```
   **Then, when Dolev is in the chat, ask the same questions in the question window**
   (`AskUserQuestion`; `reference/chat-decisions.md`): one question
   per open question, at most four per call, your recommendation first with "(מומלץ)". The
   label moves first, so a run nobody answers is still in the right state. His answer in the
   window counts like an answer in the issue: tick the questions in the open-questions section
   with his decision, move the issue to `status:explore`, and finish the plan in this same run
   (step 2, "Dolev answered your questions"). It then ends on the ready path, with no question
   about approving it. An answer that arrives in GitHub instead comes back through the scan of
   step 1 and ends the same way.

8. End the run with a summary in Hebrew: which issues moved to `status:ready-to-execute` with
   their branch, and which moved to `status:plan-questions` and what was asked. Blocked issues
   get a line of their own, "דולגו, חסומות", each with its open blockers (step 1). Issues the
   gate sent back get a line of their own, "חזרו לבקלוג: אין חלק באפיון", each with what comes
   next as its comment says (step 2): "המתזמר יכתוב לה אפיון" in the current sprint, otherwise
   "תכתוב אפיון ל-#N". Confirm with `git status --short --branch` that the working copy is exactly as you
   found it.

   **Then the code starts, in this session** (S-1.64): run `dev-code` on each issue this run
   moved to `status:ready-to-execute`, one after the other, in the order of `rank_issues.py`,
   each with its own PR and hand-off (`reference/git-flow.md`, "כמה issues בריצה אחת"). There
   is no approval question: Dolev approves the code in the review of the PR, and a comment on
   the plan after the code started comes there too. A run with nobody in the chat does the same.
   Before each, one line in the chat: the plan is written and the code starts, with the issue's
   link. The exceptions below get their own line instead.
   - **Blocked meanwhile** (an open "Blocked by" link on an issue Dolev named and asked to plan
     anyway, or one added between the plan and the code): it stays `status:ready-to-execute`,
     one line in the chat with its blocker, and on to the next. `dev-code` skips it until the
     blocker closes.
   - **Costs money** (`costs-money`): its code waits for Dolev's approval of the expense; one
     line in the chat, and on to the next.
   - **An orchestrator's child** (its contract says so, `reference/orchestrate.md`) goes on to
     `dev-code` like any run (S-2.17), with no chat line and the exceptions above. Before the
     code, one check of what the orchestrator sees, in the background (`run_in_background`):
     ```bash
     python "$HOME/.claude/skills/dev-setup/scripts/sprint_state.py" --may-code <N> --wait 30
     ```
     Exit 0: `dev-code` on it, skipping its step 1 (the gate was just checked). Exit 1, its JSON
     says why: `wip.open` false (three or more in review), or `overlaps` still there after 30
     minutes (the other issues and their files). Then a comment on the issue with that reason,
     the label stays `status:ready-to-execute`, and the turn ends: the orchestrator asks about
     the gate in its window, or opens a coding child once the overlap ends. Exit 2 (the issue
     is not open, bad input): a comment with the error, and the turn ends.
     Outside an orchestrator nothing changes: `dev-code` checks the gate in its step 1.

## Golden rules

- Never write feature code in this phase, and never `git checkout` in the shared working copy.
- A dependency the plan relies on is a "Blocked by" link, not only a sentence in the plan.
- Never plan an issue with an open "Blocked by" link, unless Dolev named it and explicitly asked.
- A task without a spec part gets no plan: it goes back to the backlog (step 2).
- Never guess on an unclear issue; take the question path.
- The spec part is the approved "what": the plan never widens it. A wider request is a spec
  update first (`dev-spec`).
- A plan is never a gate: a plan with no open question starts the code, with no approval
  question (step 8). An open question is the only stop.
- Never touch an issue whose status is not Claude's turn, unless Dolev named it or chose it in
  the question window.
- A decision comes only from Dolev himself (`reference/chat-decisions.md`).
- A comment is for questions only (the question path). A change Dolev asks for is an edit to
  the plan with a line in its log, and content for another issue is an edit to that issue.
- At most three issues planned per run. Each ready plan then runs `dev-code`, one after the other (step 8).
- Split for size, link for dependency. An issue merges into another, on Dolev's OK, only when
  it has no PR of its own, or when two small issues overlap in files, neither has a PR yet,
  and together they are still one PR that can be reviewed on its own (`reference/dependencies.md`).
- The sprint scope holds: a scan stays in the current milestone, and Claude never assigns
  one (`reference/pipeline.md`).
- Never resolve an open question by picking the option that is easiest to implement. Ask,
  even when it costs a round trip.
