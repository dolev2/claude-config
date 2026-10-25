---
name: dev-setup
description: Installs Dolev's GitHub × Claude Code issue pipeline in the current repo — the owner:/status:/area: labels, a check that the shared task and bug issue forms reach the repo, the label↔board sync workflow, the open-questions gate, sprint milestones, a linked Project board, and a pointer in CLAUDE.md — so that dev-issue, dev-next, dev-plan, dev-code and dev-ship work there. Use whenever Dolev asks to set up, install, bootstrap or add "the pipeline" / "הצינור" / "the workflow from CRM" to a repo, starts a new project and wants the same flow, or when another dev-* skill reports the pipeline is missing. Also holds the shared reference doc and scripts the other dev-* skills use.
---

# Set up the pipeline in a repo

This skill folder is also the shared home of the pipeline:

- `reference/pipeline.md`: the mechanism every dev-* skill follows (labels, phases, gates).
- `scripts/pipeline_info.py`: reads everything repo-specific from the repo itself.
- `scripts/rank_issues.py` (+ `test_rank_issues.py`): the sprint ranking.
- `scripts/board_views.py` (+ `test_board_views.py`): the board's two views, "ספרינט נוכחי" and "הכל".
- `scripts/test_open_questions_gate.py`, `scripts/test_project_sync.py`: tests for the two shared
  actions. Run them all with pytest after any change here.
- `actions/open-questions-gate/`: the open-questions gate, a composite action every repo calls.
  There is one copy of the gate, here; repos do not get a copy of the script.
- `actions/project-sync/`: the label ↔ board sync, a composite action every repo with a board calls.
  It reads the marker name from `SYNC_MARKER` and the Area options from the board itself.
- `templates/.github/`: the two short workflows that call the actions.
- `templates/README.md`: the skeleton of a repo's file guide (step 6).

The issue forms are not here. They live once, in the public repo `dolev2/.github`, and GitHub
serves them to every repo of the account that has no `.github/ISSUE_TEMPLATE` of its own.

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
| file guide in `README.md` | only if `missing_files` names it | the description line of a new `README.md` |

Without a board the pipeline still works: labels are the source of truth. Then skip step 4
and `sync-project.yml`, and keep the gate.

**A board costs Actions minutes on a private repo.** `sync-project.yml` polls every 15
minutes, and the free account's 2,000 minutes a month are shared by all private repos. GitHub
drops most scheduled runs in practice (CRM: 9 in about 28 hours, 2026-10-24), so this is a
note for Dolev in the board row, not a reason to skip the board.

## Step 2: Labels

Exact names; the skills and scripts read them. List what exists first:

```bash
gh label list --limit 300 --json name,description --jq '.[] | "\(.name)\t\(.description)"'
```

Create only the labels that are missing, without `--force`: it would silently overwrite the
description and colour of a label that already exists (a new repo already has GitHub's default
`bug`, "Something isn't working"). An existing label with the right name is kept as is; if its
description differs from the one below, show both to Dolev and change it only on his yes
(`gh label edit <name> --description ...`).

```bash
L() { gh label create "$1" --color "$2" --description "$3" || echo "FAILED $1"; }
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

The issue forms are not copied. Check `issue_forms` from step 0:

- `<owner>/.github`: the repo gets the shared forms. Nothing to do.
- `repo`: the repo has its own `.github/ISSUE_TEMPLATE/`, which hides every shared form, not
  only the files it overrides. Show Dolev the diff against `dolev2/.github` and offer to
  delete the local folder.
- empty (`missing_files` names `.github/ISSUE_TEMPLATE`): there are no forms anywhere. Stop and
  tell Dolev that `<owner>/.github` is missing.

Copy from `$HOME/.claude/skills/dev-setup/templates/.github/` into the repo's `.github/`,
only what is missing:

- `workflows/open-questions-gate.yml`: as is. It calls the shared action
  `dolev2/claude-config/skills/dev-setup/actions/open-questions-gate@main`; there is no script to copy.
  A repo that still has `.github/scripts/check_open_questions.py` from an older install: replace
  its workflow with the template and delete the script (show Dolev the diff first).
- `workflows/sync-project.yml`: as is, when there is a board. It calls the shared action
  `dolev2/claude-config/skills/dev-setup/actions/project-sync@main`; there is no script to copy.
  A repo that still has `.github/scripts/sync_project.py`: first set `SYNC_MARKER` to the marker
  name its issues already carry (the literal in that script), then replace the workflow and
  delete the script.

Then set the marker name the sync reads. It is required: without it the sync refuses to run,
and a wrong name makes every issue look unsynced, so the stale board wins over the labels:

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
  --single-select-options "Backend,Frontend,Both,Infra"   # the agreed areas' option texts
gh variable set PROJECT_NUMBER --body <number>
```

The Area option texts follow one rule: the label suffix, capitalised; an acronym stays
upper-case, so `area:seo` is `SEO`. The sync matches labels to options by that rule, so
nothing else lists the areas.

`gh project` needs the `project` scope: if it is refused, ask Dolev to run
`gh auth refresh -s project`, and wait.

**Status is the built-in field**, so it is not created but rewritten. Its options must match
`STATUS_OPTIONS` in `dev-setup/actions/project-sync/sync_project.py` exactly. Find its id, then replace its options:

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

The views come after the milestones, at the end of step 5: the sprint view filters on one.

## Step 5: Milestones and repo settings

```bash
gh api repos/{owner}/{repo}/milestones -f title="<name>" -f description="<נושא בעברית>"
gh repo edit --delete-branch-on-merge
```

Create milestones in sprint order: the lowest number is the current sprint.

The gate workflow resolves its action from `dolev2/claude-config`, which is private. That works
only while claude-config shares its actions with the owner's other repos, and only for private
repos (on a user account, a private repo's actions reach only that user's private repos):

```bash
gh api repos/dolev2/claude-config/actions/permissions/access --jq .access_level   # expect: user
gh repo view --json visibility --jq .visibility                                  # expect: PRIVATE
```

Anything other than `user`, or a public repo: tell Dolev. Without it every gate run fails on
"Unable to resolve action".

With a board, give it its views now that the milestones exist:

```bash
python "$HOME/.claude/skills/dev-setup/scripts/board_views.py" --dry-run
python "$HOME/.claude/skills/dev-setup/scripts/board_views.py"
```

It turns the board's empty "View 1" into "ספרינט נוכחי" (Status columns, filtered to the
current sprint) and adds "הכל" (a table). It deletes nothing and skips a view that already
exists. If it reports that the sprint view has no columns, ask Dolev to choose "Column by:
Status" in the board; the API cannot set it. From then on the board sync moves the filter
to each next sprint by itself (reference doc, "ספרינטים").

## Step 6: CLAUDE.md

Add a short section to the repo's `CLAUDE.md` (create the file only if Dolev agrees):

```markdown
## צינור העבודה
משימות מנוהלות כ-issues ב-<owner/repo>, עם תוויות `status:*` / `owner:*`<, ולוח Project מס' N>.
ה-milestones הם הספרינטים. המנגנון: הסקילים `dev-issue`, `dev-next`, `dev-plan`, `dev-code`,
`dev-ship` (ב-`~/.claude/skills/`), והמסמך `dev-setup/reference/pipeline.md`.
```

Keep `CLAUDE.md` to what is specific to this repo: where its layers and shared components
live, where its design tokens come from, its glossary, its commands. The code rules in
`~/.claude/rules/` load in every session, so a rule already written there is not repeated
here; if the file already repeats one, point it out to Dolev rather than deleting it.

**The file guide.** Every repo has one (`~/.claude/rules/code-general.md`): a "מדריך קבצים"
section in `README.md` that says, per folder, what each file is and why it exists. When
`missing_files` names `README.md (file guide)`:

- no `README.md`: create it from `$HOME/.claude/skills/dev-setup/templates/README.md`;
- a `README.md` without the section: append the section from the template at its end, and
  leave the rest of the file untouched.

Fill the tables from the files actually in the repo (`git ls-files`), one table per top-level
folder; a folder of many similar files gets one row. Never leave the skeleton empty, and never
guess a file's purpose: read the file, or ask Dolev. Then add one line to `CLAUDE.md`:

```markdown
- מדריך הקבצים (מה כל קובץ ולמה הוא קיים): [README.md](README.md).
```

Also make sure it has a tests section with the exact commands; `dev-code` and `dev-ship` run
whatever it says. If there is none, ask Dolev for them rather than guessing.

## Step 7: Verify and hand over

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

Expect `ready: True` and `missing_files: []` (the sync files are allowed missing when there
is no board). The file changes are uncommitted: offer to ship them with `dev-ship`. Then tell
Dolev what is left for him: the `PROJECT_TOKEN` secret and the first issues (`dev-issue`).

## Golden rules

- Nothing is written to GitHub before Dolev agrees to the list in step 1.
- Never overwrite an existing workflow, script, issue form or label description silently.
- Never handle the token. Never rename a sync marker that issues already carry.
- Label names and Status option names are a contract with the scripts: exact text only.
