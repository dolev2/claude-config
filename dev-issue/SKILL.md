---
name: dev-issue
description: Opens new GitHub issues in the current repo in Dolev's pipeline format — tasks, bugs, backlog ideas, and the sub-issues of a task being split up — with the right body sections, labels, milestone, sub-issue links and native "Blocked by" dependency links. Use in any of Dolev's repos whenever he asks to open, add, file or split a task or bug ("תפתח משימה", "תפרק את זה ל-issues", "תוסיף לבקלוג"), to break an issue into sub-issues, or to put an idea in the backlog. Works in any repo that has the pipeline labels; if the repo has its own repo-specific issue skill, use that instead. Pairs with dev-plan, which picks up what this skill creates.
---

# Open issues

The entry point of Dolev's GitHub × Claude Code pipeline: everything `dev-plan` later plans
starts as an issue opened here or from the GitHub issue form. An issue opened here must be
indistinguishable from one opened through the form, plus the links the form cannot make.

## Step 0: Orient

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

- `repo_skills` lists a repo-specific skill for opening issues? Use it
  instead and stop here.
- `ready` is `False`? The pipeline is not installed in this repo. Offer `dev-setup` and stop.
- Note `human` (the `owner:<human>` label), `area_labels`, and `current_sprint`.

## Read first

- **`$HOME/.claude/skills/dev-setup/reference/pipeline.md`**: the label vocabulary,
  milestones, and the "תלויות" section on "Blocked by" links.
- **The repo's `CLAUDE.md`**: its sources of truth, and its rules about business data. Do
  not invent prices, values or business rules. What is missing goes into "שאלות פתוחות" as an
  unticked box, not into the text.
- **`.github/ISSUE_TEMPLATE/task.yml` and `bug.yml`**: the exact sections of the body.

## Step 1: Agree on the list before creating anything

Opening issues writes to the board Dolev works from, and deleting an issue is not something
this pipeline does. So first show Dolev, in chat, the issues you intend to open: title, one
line of scope, kind (task / bug / backlog), milestone, parent, and blockers. Create them only
after he agrees. When he has already dictated the exact list, that is the agreement.

How to split a task, when that is the request:
- **One issue = one PR that can be reviewed on its own.** Split by user-visible capability (a
  screen, a page section, an endpoint group, a command, a module), not by layer ("the HTML",
  "the CSS").
- **Shared infrastructure goes into the issue that needs it first**, not into an issue of its
  own built ahead of any user. If an existing issue already owns that ground, extend its body
  instead of opening a new one.
- **Ideas outside the current scope** go to the backlog: no milestone.

## Step 2: Write the body

Exactly the sections of the repo's `.github/ISSUE_TEMPLATE/task.yml`, in its order and with
its wording (Hebrew or English), because `dev-plan` and `open-questions-gate.yml` read them by
heading. Use the heading level the repo's existing issues use: issue-form bodies come out as
`###`, some repos write `##`. Take the dependency line's wording from CLAUDE.md if it gives one
(`Depends on:`). With the standard Hebrew template:

```markdown
### מה רוצים

<what should happen and why; for a sub-issue, which part of the parent it covers>
*בדיקה:* <how Dolev will know it works>

### אזור

<one of the template's area options>

### הקשר / קישורים

<parent and source, with a link to the repo's source of truth from CLAUDE.md>
תלוי ב: #A, #B.

---
### Plan

_טרם נכתבה תוכנית._

### שאלות פתוחות

_אין שאלות פתוחות._
```

For a bug, follow `bug.yml` instead (with the standard template: משימה קשורה / מה קורה / מה
היה אמור לקרות / אזור / Plan / שאלות פתוחות).

**Do not write the hidden sync marker (`<!-- <sync_marker>: ... -->`) yourself, and never
edit an existing one.** `sync_project.py` owns it: it records the last synced state, and a
side that differs from it is treated as the side that changed. A hand-written marker that
matches the new labels makes the stale board look like the newer edit, and the sync then
reverts the labels. To change an issue's state, change its labels and leave the marker alone.

Write the body to a file with LF line endings and pass `--body-file`, never an inline string
with `\n` (reference doc, "סעיף ה-Plan").

A business detail a person still owes (a price, a client's answer) is an unticked open
question in the body, not a "Blocked by" link to some other issue.

## Step 3: Create, with labels and milestone

| kind | labels | milestone |
|---|---|---|
| task | `task`, `area:*`, `owner:claude`, `status:explore` | the sprint it belongs to |
| bug | `bug`, `area:*`, `owner:claude`, `status:ready-to-execute` | the related task's |
| backlog idea | `task`, `area:*`, `owner:<human>`, `status:backlog` | none |
| umbrella (parent split into sub-issues) | keeps `task`, `area:*`; becomes `owner:<human>`, `status:backlog` | unchanged |
| decision (only if the repo has a `decision` label) | `decision`, `owner:<human>`, no `status:*` | the sprint that waits on it |

Use only `area:*` labels that exist in the repo (`area_labels`). A decision issue's body has
only the goal and context sections: it is closed by Dolev's decision in a comment, not by a PR.
If the repo's CLAUDE.md says new issues or decisions are also recorded elsewhere (a tracker
doc), do that too.

```bash
gh issue create --title "<title>" --body-file <file> \
  --label task --label area:frontend --label owner:claude --label status:explore \
  --milestone "<milestone>"
```

The milestone is Dolev's call: use the one he named or the one the parent carries, and ask
when neither exists. If the repo numbers its tasks in titles, sub-issues continue the
parent's numbering (`13א.`, `13ב.`), so the board reads in order.

## Step 4: Link

1. **Sub-issue**: attach each one to its parent (the API takes the child's `id`, not its
   number):
   ```bash
   CID=$(gh api repos/{owner}/{repo}/issues/<child> --jq .id)
   gh api -X POST repos/{owner}/{repo}/issues/<parent>/sub_issues -F sub_issue_id=$CID
   ```
2. **Blocked by**: one link per `#B` on the `תלוי ב:` line, with the commands in the
   "תלויות" section of the reference doc. The line and the links must list the same issues.
   Link a sub-issue to its own blockers, not only through the parent: Execute checks the
   issue it is about to start.
3. **The parent's body**: when splitting, rewrite the parent's "מה רוצים" as an umbrella: a
   checklist of the sub-issues (`- [ ] #29 ...`) and what stayed out of scope. Then relabel
   it as an umbrella (labels only).

## Step 5: Verify and report

```bash
gh api repos/{owner}/{repo}/issues/<parent>/sub_issues --jq '.[] | "\(.number) \(.title)"'
gh api repos/{owner}/{repo}/issues/<N>/dependencies/blocked_by --jq '[.[].number]'
gh issue view <N> --json labels,milestone --jq '[.labels[].name], .milestone.title'
```

Report each new issue to Dolev, in Hebrew, as a link with its title, milestone and blockers. If the repo has
`sync-project.yml`, a board column that has not updated yet catches up within 15 minutes.

## Golden rules

- Never create issues Dolev has not agreed to, and never delete one.
- Never write or edit the sync marker.
- Never invent business data in an issue; missing data is an unticked open question.
- Every `תלוי ב:` entry has a matching "Blocked by" link, and the other way round.
- Never assign a milestone on your own judgement.
