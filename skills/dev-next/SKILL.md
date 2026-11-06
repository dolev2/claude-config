---
name: dev-next
description: Picks the next issue to work on in the current repo — the open issue in the current sprint (milestone) that the most other sprint issues wait on through "Blocked by" links — and routes it to dev-plan or dev-code by its status, or says plainly when it is waiting for Dolev. Use in any of Dolev's repos whenever he says "let's work on the next task", "בוא נעבוד על המשימה הבאה", "מה הבא", "what's next", or asks what is blocking the sprint. Also use it when he asks to review or fix the order of the sprint ("תבדוק את סדר הספרינט", "review the sprint order"): a full review of the sprint's "Blocked by" links that proposes links to add or remove and issues to merge. Works in any repo that has the pipeline labels; if the repo has its own repo-specific next-issue skill, use that instead.
---

# The next issue

An entry point, not a phase: this skill decides **which** issue, then hands it to the phase
that owns its status. It writes no plan and no code itself.

## Step 0: Orient

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

- `repo_skills` lists a repo-specific next-issue skill? Use it instead.
- `ready` is `False`? Offer `dev-setup` and stop.
- In a cloud session (`CLAUDE_CODE_REMOTE=true`), run every `gh` command below through the table in `reference/cloud.md`.
- When routing in step 3, prefer the repo's own plan/code skills over `dev-plan` /
  `dev-code` if `repo_skills` has them.

## Read first

In **`$HOME/.claude/skills/dev-setup/reference/`**: `pipeline.md` (the labels, the sprint) and `dependencies.md`: the
ranking rule and why this skill ranks without status tiers, while the phases put the status
tier first. In both, `process` and `bug` issues come before the rest, then weight decides.
Its sub-section "בדיקת הסדר" holds what the audit below finds, and the rule for merging.
The review of the sprint order edits issue bodies, so it also reads `issue-body.md` there.

## Steps

1. Rank the whole sprint:
   ```bash
   python "$HOME/.claude/skills/dev-setup/scripts/rank_issues.py"
   ```
   `process` and `bug` issues come first, each group by weight. Each row is `#N`, how many
   sprint issues wait on it, its status, its kind (`process`, `bug` or `-`), its title, and
   `BLOCKED by #…` if it has an open blocker. The first line names the sprint. Issues
   labelled `costs-money` are on hold until Dolev approves the expense: they are not ranked,
   and the last line lists them (`On hold, costs-money: …`). Never pick one, and never
   remove the label; only Dolev lifts the hold. A line `Active, no sprint: …` lists open
   issues in the pipeline (past backlog, short of done) that have no milestone at all: no
   scan reaches them, so step 6 reports them.

   Then check the links behind that ranking:
   ```bash
   python "$HOME/.claude/skills/dev-setup/scripts/audit_sprint.py"
   ```
   Mention each finding to Dolev in one line, before routing. A finding about the issue you
   pick (a `MENTION` of something it may need, an `OUTSIDE` blocker) comes first: it can mean
   the issue is not really next. Fix nothing here; findings are signals, and the fixes are the
   full review below, on his request. `(no findings)`: say nothing.

2. Pick the first row, top down, that:
   - has no `BLOCKED by`. A blocked issue is never the next one; what blocks it ranks above
     it anyway, since it carries at least the same weight plus one;
   - is not `status:backlog` with `0 waiting`. That is a sprint umbrella or an idea nobody
     waits on, not work to pick up;
   - is not a `decision` issue (no status) with `0 waiting`, unless nothing
     else is left. A decision that others wait on is a real bottleneck and stays a candidate.

   When the bottleneck is an issue on hold (a row is `BLOCKED by` one), say so: the hold is
   what stops that work, and lifting it is Dolev's call.

   No row left means nothing in the sprint can move. Say so, show the ranking, and stop.
   Never reach outside the milestone.

3. Route it by status. The status alone says whose turn it is (`reference/pipeline.md`):

   | status | whose turn | what to do |
   |---|---|---|
   | `explore` | Claude | run **dev-plan** on this issue only |
   | `ready-to-execute`, `needs-repair` | Claude | run **dev-code** on this issue |
   | none (`decision`) | Dolev | his decision, closed with a comment |
   | `waiting-approval` | Dolev | his approval of the plan |
   | `plan-questions` | Dolev | his answers, in the issue's "שאלות פתוחות"; then it goes back to `status:explore` |
   | `in-review` | Dolev | his review of the PR, then a fix (`needs-repair`) or his request in the chat to merge it (dev-ship) |
   | `backlog` | Dolev | handing it over: writing it up and moving it to `status:explore` |

   Before routing, tell Dolev in Hebrew, in one or two lines, which issue you picked and why: whether it
   is a `process` or `bug` issue, how many issues wait on it, and the next one or two below it. Then invoke the phase skill with the
   issue number. Both phase skills take the issue Dolev named over their own ranking, and
   still apply every gate of their own (the WIP gate, the blocked check, the sprint).

4. **When the top issue waits for Dolev, do not route around it silently.** Say what it
   waits for (the table above), with a link to the issue, then name the first row in Claude's
   turn below it that step 2 would pick, and ask whether to work on that one meanwhile. Doing
   his part (approving, answering, merging, relabelling) is never yours.

5. If the ranking shows an issue in `status:needs-repair` that you did not
   pick, mention it: a repair is work Dolev already reviewed, and `dev-code` on its own would
   take it first.

6. If the ranking ends with `Active, no sprint: …`, report each of those issues in the same
   message: a link with its title, and what it waits for (the table in step 3). They fell out
   of every sprint, often on the way into the pipeline (WayOut #42 and #117 came from Trello
   like that, claude-config #55). Which sprint they belong to is Dolev's call: never assign
   one, and never pick one of them as the next issue.

## Review of the sprint order

On Dolev's request only, instead of the steps above. It picks no issue.

1. Read the sprint in one pass:
   ```bash
   python "$HOME/.claude/skills/dev-setup/scripts/audit_sprint.py" --json
   ```
   Each issue's goal, the files its Plan lists, its open blockers, whether it has a PR, and
   the findings. Open the full body of an issue only where the goal is not enough to judge.
2. Judge every pair that could depend on each other, not only the findings: does one need
   something the other delivers before it can start? Judge each finding too:
   - `MENTION`: a dependency, or only a reference?
   - `OVERLAP`: a collision risk, never a link by itself. When it says `merge-candidate`,
     check whether both together are still one PR that can be reviewed on its own; if so,
     propose merging them.
   - `LINE-MISMATCH`, `OUTSIDE`, `CYCLE`: which link is wrong.
3. Show the proposals as one table: the change (add a link, remove a link, merge), the
   issues with their titles, and why, in one line each. Ask with the questions tool which to
   apply (multiple choice, the ones you recommend first).
4. Apply only what he chose: a link and the `תלוי ב:` line together (`reference/dependencies.md`); a merge through `dev-issue`'s rules, the surviving issue's body taking the
   other's goal and its Plan sent back to `status:explore`. Then run `rank_issues.py` again
   and show what moved.

## Golden rules

- One issue per run of this skill, handed to one phase.
- Never pick a blocked issue, an issue outside the current sprint, or one without a milestone.
- Never take Dolev's step for him because it is the bottleneck. Report it.
- The ranking lives in `rank_issues.py`. Do not re-derive it by hand.
- A link, a removed link or a merge from the review is applied only after Dolev chose it.
