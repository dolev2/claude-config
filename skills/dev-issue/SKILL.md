---
name: dev-issue
description: Opens new GitHub issues in the current repo in Dolev's pipeline format — tasks, bugs, backlog ideas, and the sub-issues of a task being split up — with the right body sections, labels, milestone, sub-issue links and native "Blocked by" dependency links. Use in any of Dolev's repos whenever he asks to open, add, file or split a task or bug ("תפתח משימה", "תפרק את זה ל-issues", "תוסיף לבקלוג"), to break an issue into sub-issues, to put an idea in the backlog, or to break a merged spec into one issue per part ("תפרק את האפיון"). Works in any repo that has the pipeline labels; if the repo has its own repo-specific issue skill, use that instead. Pairs with dev-plan, which picks up what this skill creates.
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
- In a cloud session (`CLAUDE_CODE_REMOTE=true`), run every `gh` command below through the table in `reference/cloud.md`.
- Note `area_labels`, `current_sprint`, and `issue_forms`.

## Read first

- **In `$HOME/.claude/skills/dev-setup/reference/`**: `pipeline.md` (the label vocabulary, milestones),
  `issue-body.md` (editing a body), `dependencies.md` ("Blocked by" links) and `specs.md`
  (the spec line, and the breakdown of a merged spec into issues).
- **The repo's `CLAUDE.md`**: its sources of truth, and its rules about business data. Do
  not invent prices, values or business rules. What is missing goes into "שאלות פתוחות" as an
  unticked box, not into the text.
- **The task and bug forms**: the exact sections of the body. `issue_forms` says where they
  live: `repo` is the repo's own `.github/ISSUE_TEMPLATE/`; `<owner>/.github` is the account's
  default forms, which GitHub serves to every repo without forms of its own:
  ```bash
  gh api repos/<owner>/.github/contents/.github/ISSUE_TEMPLATE/task.yml -H "Accept: application/vnd.github.raw"
  ```
  (`bug.yml` next to it.) `unknown (no access from this session)` is not a place: the API
  cannot reach `<owner>/.github` from here (a cloud session). Read the forms from a read-only
  clone instead, which the session's git proxy serves for a public repo without attaching it:
  `git clone --depth 1 https://github.com/<owner>/.github <scratchpad>/owner-github`.

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

Exactly the sections of the task form (`task.yml`, from where `issue_forms` says), in its order and with
its wording (Hebrew or English), because `dev-plan` and `open-questions-gate.yml` read them by
heading. Use the heading level the repo's existing issues use: issue-form bodies come out as
`###`, some repos write `##`. Take the dependency line's wording from CLAUDE.md if it gives one
(`Depends on:`). With the standard Hebrew template:

```markdown
### מה רוצים

<what should happen and why; for a sub-issue, which part of the parent it covers>
*בדיקה:* <how Dolev will know it works>

### הקשר / קישורים

<parent and source, with a link to the repo's source of truth from CLAUDE.md>
תלוי ב: #A, #B.
אפיון: docs/specs/<repo>.md S-<n>.<m>

---
### Plan

_טרם נכתבה תוכנית._

### שאלות פתוחות

_אין שאלות פתוחות._
```

**The `אפיון:` line** names the part the task implements (the format:
`$HOME/.claude/docs/specs/README.md`). Write it when the topic is already in a spec: read the files in
`docs/specs/` on `origin/<default>` and find the part. No part fits: leave the line out, and
`dev-plan` drafts a new part with the plan (`reference/specs.md`). A backlog idea gets no line:
it is a proposal, and gets its spec when Dolev asks for one (`dev-spec`).

For a bug, follow `bug.yml` instead (with the standard template: משימה קשורה / מה קורה / מה
היה אמור לקרות / Plan / שאלות פתוחות).

The area is a label only (`area:*`, below), not a section of the body. Older issues may still
carry an `אזור` section; leave it as it is.

**To change an issue's state, change its labels only.** The board follows the labels, and a
card moved by hand goes back on the next sync (`reference/setup.md`).

Write the body to a file with LF line endings and pass `--body-file`, never an inline string
with `\n` (`reference/issue-body.md`).

A business detail a person still owes (a price, a client's answer) is an unticked open
question in the body, not a "Blocked by" link to some other issue.

## Step 3: Create, with labels and milestone

| kind | labels | milestone |
|---|---|---|
| task | `task`, `area:*`, `status:explore` | the sprint it belongs to |
| bug | `bug`, `area:*`, `status:ready-to-execute` | always `current_sprint` |
| process (work management, rules, aligning with claude-config) | `process` added to the task's labels | always `current_sprint` |
| manual task (only Dolev can do it: Claude has no access) | `task`, `area:*`, `status:plan-questions`, with what he must check or answer as unticked boxes in the open-questions section (`reference/pipeline.md`, the `status:plan-questions` row) | the sprint it belongs to |
| backlog idea | `task`, `area:*`, `status:backlog` | none |
| lesson (`reference/lessons.md`): the body's "מה רוצים" holds the lesson's four fields, "הקשר / קישורים" its source, and no `אפיון:` line | `task`, `process`, `area:*`, `status:explore`, in the repo where the lesson lives (`~/.claude`: dolev2/claude-config) | that repo's current sprint when Dolev chose "open a task" in the question window (that choice is the agreement of step 1); with nobody in the chat, `status:backlog` and none |
| umbrella (parent split into sub-issues) | keeps `task`, `area:*`; becomes `status:backlog` | unchanged |
| decision (only if the repo has a `decision` label) | `decision`, no `status:*` (Dolev's turn by its kind) | the sprint that waits on it |

Add `process` to any task that is about how the work is managed rather than the project itself: the pipeline, compliance with the rules in `~/.claude/rules/`, or aligning the repo with claude-config (a lint drift, a missing file guide). The definition is in the vocabulary table of `reference/pipeline.md`. Not in claude-config itself, where every issue is one.

Use only `area:*` labels that exist in the repo (`area_labels`). A decision issue's body has
only the goal and context sections: it is closed by Dolev's decision in a comment, not by a PR.
If the repo's CLAUDE.md says new issues or decisions are also recorded elsewhere (a tracker
doc), do that too.

```bash
gh issue create --title "<title>" --body-file <file> \
  --label task --label area:frontend --label status:explore \
  --milestone "<milestone>"
```

The milestone is Dolev's call: use the one he named or the one the parent carries, and ask
when neither exists. The exception is a bug or a `process` issue: it always goes into
`current_sprint`, without asking (agreed in claude-config #38). If the repo numbers its tasks in titles, sub-issues continue the
parent's numbering (`13א.`, `13ב.`), so the board reads in order.

## Step 4: Link

1. **Sub-issue**: attach each one to its parent (the API takes the child's `id`, not its
   number):
   ```bash
   CID=$(gh api repos/{owner}/{repo}/issues/<child> --jq .id)
   gh api -X POST repos/{owner}/{repo}/issues/<parent>/sub_issues -F sub_issue_id=$CID
   ```
2. **Blocked by**: one link per `#B` on the `תלוי ב:` line, with the commands in
   `reference/dependencies.md`. The line and the links must list the same issues.
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
`sync-project.yml`, a board column that has not updated yet catches up within a few hours.

## Mode: breaking down a spec (פירוק אפיון)

After a spec PR merges (`dev-ship` offers it, step 8), or when Dolev asks to break a spec into
issues. The rules: `reference/specs.md`, "הפירוק ל-issues".

1. **Read the merged file** from `origin/<default>` (`git fetch` first), and list its open parts
   that no open issue points at:
   ```bash
   python "$HOME/.claude/skills/dev-setup/scripts/spec_check.py" --table --ref origin/<default>
   ```
   The rows in state "אין issue" are the parts to open.
2. **Step 1 of this skill, unchanged:** show Dolev the list before creating anything, one issue
   per part: the title (the part's name), the part's id, the milestone (his call, as always),
   and the blockers. A blocker comes **only** from a dependency written in the spec ("תלוי
   ב-S-1.2": blocked by the issue of S-1.2, new or existing). A dependency that seems missing is
   a question to him, never a guessed link; if he agrees, the spec is updated first
   (`dev-spec`).
3. **Each body** follows step 2: "מה רוצים" says in a line or two which part it implements and
   how Dolev will know it works, without copying the part; "הקשר / קישורים" links the proposal
   and holds the `תלוי ב:` and `אפיון:` lines. Labels and milestone as step 3 (a task); links
   as step 4.
4. **Close the proposal** once every issue exists and is linked: a comment that points at the
   spec file and lists the new issues, then closed as completed:
   ```bash
   gh issue comment <proposal> --body-file <file>
   gh api -X PATCH repos/{owner}/{repo}/issues/<proposal> -f state=closed -f state_reason=completed
   ```
   A spec written for a task (like claude-config #230) has no proposal: nothing to close.
5. Report as in step 5, with the part id next to each new issue.

## Golden rules

- Never create issues Dolev has not agreed to, and never delete one.
- Never invent business data in an issue; missing data is an unticked open question.
- Every `תלוי ב:` entry has a matching "Blocked by" link, and the other way round.
- In a breakdown, a link comes only from a dependency written in the spec; never guess one.
- Never assign a milestone on your own judgement, except `current_sprint` for a bug or a
  `process` issue.
