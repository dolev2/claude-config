---
name: dev-setup
description: Installs Dolev's GitHub × Claude Code issue pipeline in the current repo — the owner:/status:/area: labels, the task and bug issue forms, the label↔board sync workflow, the open-questions gate, sprint milestones, a linked Project board, and a pointer in CLAUDE.md — so that dev-issue, dev-next, dev-plan, dev-code and dev-ship work there. Use whenever Dolev asks to set up, install, bootstrap or add "the pipeline" / "הצינור" / "the workflow from CRM" to a repo, starts a new project and wants the same flow, or when another dev-* skill reports the pipeline is missing. Also holds the shared reference doc and scripts the other dev-* skills use.
---

# Set up the pipeline in a repo

This skill folder is also the shared home of the pipeline:

- `reference/pipeline.md`: the mechanism every dev-* skill follows (labels, phases, gates).
- `scripts/pipeline_info.py`: reads everything repo-specific from the repo itself.
- `scripts/rank_issues.py` (+ `test_rank_issues.py`): the sprint ranking.
- `scripts/test_templates.py`: tests for the template scripts. Run both with pytest after any change here.
- `templates/.github/`: the issue forms, the sync workflow, and the open-questions gate.

Read `reference/pipeline.md` before step 1, so you know what each piece is for.

## Step 0: What is already there

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

`ready: True` and `missing_files: []` means it is installed. Say so and stop. Otherwise
note what is missing; only that gets added. Never overwrite an existing workflow, script or
issue form: show the diff against the template and ask.

## Step 1: Agree on the setup before writing anything

Everything here writes to GitHub (labels, milestones, a board, repo settings) or to the repo.
Show Dolev, in chat, one list, and wait for his yes:

| item | default | ask about |
|---|---|---|
| repo | from `gh repo view` | — |
| sync marker name | `<short repo name>-sync`, e.g. `crm-sync` | never changes later |
| `area:*` labels | `backend`, `frontend`, `both`, `infra` | fit this project? |
| milestones (sprints) | none | the names, in order; titles in English |
| Project board | a new user project named after the repo, linked to it | create one, reuse one, or skip |
| CI tests workflow | only if the repo has none | which commands |
| "Automatically delete head branches" | on | — |

Without a board the pipeline still works: labels are the source of truth. Then skip step 4
and `sync-project.yml`, and keep the gate.

## Step 2: Labels

Exact names; the skills and scripts read them. `--force` updates an existing label instead
of failing.

```bash
L() { gh label create "$1" --color "$2" --description "$3" --force; }
L "owner:claude"            1f6feb "מחכה ל-Claude"
L "owner:dolev"             8250df "מחכה לדולב"
L "status:explore"          c5def5 "Claude חוקר וכותב תוכנית"
L "status:plan-questions"   f9d0c4 "שאלה פתוחה על התוכנית"
L "status:waiting-approval" fef2c0 "ממתין לאישור התוכנית מדולב"
L "status:ready-to-execute" 0e8a16 "מוכן לביצוע ע\"י Claude"
L "status:needs-repair"     d93f0b "חזר ל-Claude לתיקון"
L "status:in-review"        bfd4f2 "Claude סיים, בבדיקת דולב"
L "status:done"             5319e7 "הושלם ואושר"
L "status:backlog"          ededed "רעיון/backlog, לא בצינור"
L "task"                    0052cc "משימה"
L "bug"                     d73a4a "באג"
L "has-open-questions"      d93f0b "עבר ל-status:done עם שאלה שלא נסגרה"
L "area:backend"            1d76db "צד שרת"
L "area:frontend"           b60205 "צד לקוח"
L "area:both"               5319e7 "גם וגם"
L "area:infra"              006b75 "תשתית/כלים"
```

Use the `area:*` list Dolev agreed to, not necessarily these four.

## Step 3: Files

Copy from `$HOME/.claude/skills/dev-setup/templates/.github/` into the repo's `.github/`,
only what is missing:

- `ISSUE_TEMPLATE/task.yml`, `bug.yml`, `config.yml`: change the `אזור` dropdown options to
  the agreed areas (option text = the label suffix, capitalised).
- `workflows/open-questions-gate.yml` + `scripts/check_open_questions.py`: as is.
- `workflows/sync-project.yml` + `scripts/sync_project.py`: as is, when there is a board.
  If the agreed areas differ, update `AREA_OPTIONS` in `sync_project.py` to match.

Then set the marker name the sync script reads:

```bash
gh variable set SYNC_MARKER --body "<marker>"
```

If the repo has no CI and Dolev agreed to one, write `.github/workflows/tests.yml` that runs
the repo's test commands on `pull_request` and on `push` to the default branch. Base it on the
stack actually in the repo; do not invent commands.

## Step 4: The Project board

```bash
OWNER=$(gh repo view --json owner --jq .owner.login)
gh project create --owner "$OWNER" --title "<Title>" --format json --jq .number
gh project link <number> --owner "$OWNER" --repo "$OWNER/<repo>"
gh project field-create <number> --owner "$OWNER" --name Owner --data-type SINGLE_SELECT \
  --single-select-options "Claude,Dolev"
gh project field-create <number> --owner "$OWNER" --name Area --data-type SINGLE_SELECT \
  --single-select-options "Backend,Frontend,Both,Infra"
gh variable set PROJECT_NUMBER --body <number>
```

`gh project` needs the `project` scope: if it is refused, ask Dolev to run
`gh auth refresh -s project`, and wait.

**Status is the built-in field**, so it is not created but rewritten. Its options must match
`STATUS_OPTIONS` in `sync_project.py` exactly. Find its id, then replace its options:

```bash
gh api graphql -f query='query($o:String!,$n:Int!){user(login:$o){projectV2(number:$n){field(name:"Status"){... on ProjectV2SingleSelectField{id}}}}}' \
  -F o="$OWNER" -F n=<number> --jq .data.user.projectV2.field.id
```

Write this to a file and send it with `gh api graphql --input <file>`:

```json
{"query": "mutation($id:ID!,$opts:[ProjectV2SingleSelectFieldOptionInput!]){updateProjectV2Field(input:{fieldId:$id,singleSelectOptions:$opts}){projectV2Field{... on ProjectV2SingleSelectField{options{name}}}}}",
 "variables": {"id": "<field id>", "opts": [
  {"name": "Explore (Claude)", "color": "BLUE", "description": ""},
  {"name": "Plan questions", "color": "ORANGE", "description": ""},
  {"name": "Waiting for Dolev approval", "color": "YELLOW", "description": ""},
  {"name": "Ready to execute (Claude)", "color": "GREEN", "description": ""},
  {"name": "Needs repair (Claude)", "color": "RED", "description": ""},
  {"name": "Claude done / In review (Dolev)", "color": "PURPLE", "description": ""},
  {"name": "Done", "color": "GREEN", "description": ""},
  {"name": "Backlog", "color": "GRAY", "description": ""}]}}
```

If the mutation is refused, give Dolev the eight names to type in the board's field settings.

**The token is Dolev's step, never yours.** The sync workflow needs a PAT with `project` and
`repo` in the secret `PROJECT_TOKEN`. Give him this command to run himself, and do not ask
him to paste the token into the chat:

```powershell
$t = Read-Host 'Paste token'; gh secret set PROJECT_TOKEN --body $t; Remove-Variable t
```

Views (by status, current sprint, all) are made in the board UI; the sprint view filters
`milestone:"<name>"`, which is updated by hand each sprint (reference doc, "ספרינטים").

## Step 5: Milestones and repo settings

```bash
gh api repos/{owner}/{repo}/milestones -f title="<name>" -f description="<נושא בעברית>"
gh repo edit --delete-branch-on-merge
```

Create milestones in sprint order: the lowest number is the current sprint.

## Step 6: CLAUDE.md

Add a short section to the repo's `CLAUDE.md` (create the file only if Dolev agrees):

```markdown
## צינור העבודה
משימות מנוהלות כ-issues ב-<owner/repo>, עם תוויות `status:*` / `owner:*`<, ולוח Project מס' N>.
ה-milestones הם הספרינטים. המנגנון: הסקילים `dev-issue`, `dev-next`, `dev-plan`, `dev-code`,
`dev-ship` (ב-`~/.claude/skills/`), והמסמך `dev-setup/reference/pipeline.md`.
```

Also make sure it has a tests section with the exact commands; `dev-code` and `dev-ship` run
whatever it says. If there is none, ask Dolev for them rather than guessing.

## Step 7: Verify and hand over

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

Expect `ready: True` and `missing_files: []` (the sync files are allowed missing when there
is no board). The file changes are uncommitted: offer to ship them with `dev-ship`. Then tell
Dolev what is left for him: the `PROJECT_TOKEN` secret, the board views, and the first issues
(`dev-issue`).

## Golden rules

- Nothing is written to GitHub before Dolev agrees to the list in step 1.
- Never overwrite an existing workflow, script, issue form or label description silently.
- Never handle the token. Never rename a sync marker that issues already carry.
- Label names and Status option names are a contract with the scripts: exact text only.
