---
name: dev-next
description: Picks the next issue to work on in the current repo — the open issue in the current sprint (milestone) that the most other sprint issues wait on through "Blocked by" links — and routes it to dev-plan or dev-code by its status, or says plainly when it is waiting for Dolev. Use in any of Dolev's repos whenever he says "let's work on the next task", "בוא נעבוד על המשימה הבאה", "מה הבא", "what's next", or asks what is blocking the sprint. Works in any repo that has the pipeline labels; if the repo has its own repo-specific next-issue skill, use that instead.
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
- When routing in step 3, prefer the repo's own plan/code skills over `dev-plan` /
  `dev-code` if `repo_skills` has them.

## Read first

**`$HOME/.claude/skills/dev-setup/reference/pipeline.md`**, section "סדר בתוך הספרינט": the
ranking rule and why this skill ranks without status tiers, while the phases put the status
tier first. In both, `process` and `bug` issues come before the rest, then weight decides.

## Steps

1. Rank the whole sprint:
   ```bash
   python "$HOME/.claude/skills/dev-setup/scripts/rank_issues.py"
   ```
   `process` and `bug` issues come first, each group by weight. Each row is `#N`, how many
   sprint issues wait on it, its status, its owner, its kind (`process`, `bug` or `-`), its title, and
   `BLOCKED by #…` if it has an open blocker. The first line names the sprint. Issues
   labelled `costs-money` are on hold until Dolev approves the expense: they are not ranked,
   and the last line lists them (`On hold, costs-money: …`). Never pick one, and never
   remove the label; only Dolev lifts the hold.

2. Pick the first row, top down, that:
   - has no `BLOCKED by`. A blocked issue is never the next one; what blocks it ranks above
     it anyway, since it carries at least the same weight plus one;
   - is not `status:backlog` with `0 waiting`. That is a sprint umbrella or an idea nobody
     waits on, not work to pick up;
   - is not a `decision` issue (no status, `owner:<human>`) with `0 waiting`, unless nothing
     else is left. A decision that others wait on is a real bottleneck and stays a candidate.

   When the bottleneck is an issue on hold (a row is `BLOCKED by` one), say so: the hold is
   what stops that work, and lifting it is Dolev's call.

   No row left means nothing in the sprint can move. Say so, show the ranking, and stop.
   Never reach outside the milestone.

3. Route it by status and owner:

   | status | owner | what to do |
   |---|---|---|
   | `explore`, `plan-questions` | claude | run **dev-plan** on this issue only |
   | `ready-to-execute`, `needs-repair` | claude | run **dev-code** on this issue |
   | `ready-to-execute` | human | something he does himself (a manual step, a trial run) |
   | none (`decision`) | human | his decision, closed with a comment |
   | `waiting-approval` | human | his approval of the plan |
   | `plan-questions` | human | his answers, in the issue's "שאלות פתוחות" |
   | `in-review` | human | his review of the PR |
   | `done` | human | his explicit request to merge (dev-ship) |
   | `backlog` | human | handing it over: writing it up and moving it to `status:explore` + `owner:claude` |

   Before routing, tell Dolev in Hebrew, in one or two lines, which issue you picked and why: whether it
   is a `process` or `bug` issue, how many issues wait on it, and the next one or two below it. Then invoke the phase skill with the
   issue number. Both phase skills take the issue Dolev named over their own ranking, and
   still apply every gate of their own (the WIP gate, the blocked check, the sprint).

4. **When the top issue waits for Dolev, do not route around it silently.** Say what it
   waits for (the table above), with a link to the issue, then name the first `owner:claude`
   row below it that step 2 would pick, and ask whether to work on that one meanwhile. Doing
   his part (approving, answering, merging, relabelling) is never yours.

5. If the ranking shows an `owner:claude` issue in `status:needs-repair` that you did not
   pick, mention it: a repair is work Dolev already reviewed, and `dev-code` on its own would
   take it first.

## Golden rules

- One issue per run of this skill, handed to one phase.
- Never pick a blocked issue, an issue outside the current sprint, or one without a milestone.
- Never take Dolev's step for him because it is the bottleneck. Report it.
- The ranking lives in `rank_issues.py`. Do not re-derive it by hand.
