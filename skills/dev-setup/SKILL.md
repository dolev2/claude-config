---
name: dev-setup
description: Installs Dolev's GitHub × Claude Code issue pipeline in the current repo — the status:/area: labels, a check that the shared task and bug issue forms reach the repo, the label→board sync workflow, the open-questions gate, sprint milestones, a linked Project board, and a pointer in CLAUDE.md — so that dev-issue, dev-next, dev-plan, dev-code and dev-ship work there. Use whenever Dolev asks to set up, install, bootstrap or add "the pipeline" / "הצינור" / "the workflow from CRM" to a repo, starts a new project and wants the same flow, or when another dev-* skill reports the pipeline is missing. Also holds the shared reference files and scripts the other dev-* skills use.
---

# Set up the pipeline in a repo

This skill folder is also the shared home of the pipeline:

- `reference/`: the mechanism every dev-* skill follows. `pipeline.md` is the core, and lists
  the other files and what each holds.
- `scripts/pipeline_info.py`: reads everything repo-specific from the repo itself.
- `scripts/rank_issues.py` (+ `test_rank_issues.py`): the sprint ranking.
- `scripts/lint_check.py` (+ `test_lint_check.py`): which lint settings a repo lacks, or holds
  in a copy that strays from its template. `pipeline_info.py` shows its list under `lint`.
- `scripts/port_check.py` (+ `test_port_check.py`): whether a port is busy on 127.0.0.1 or ::1,
  and a port free on both, for the review app (`reference/review-app.md`).
- `scripts/board_views.py` (+ `test_board_views.py`): the board's two views, "ספרינט נוכחי" and "הכל".
- `scripts/test_open_questions_gate.py`, `scripts/test_project_sync.py`: tests for the two shared
  actions. Run them all with pytest after any change here.
- `actions/open-questions-gate/`: the open-questions gate, a composite action every repo calls.
  There is one copy of the gate, here; repos do not get a copy of the script.
- `actions/project-sync/`: the label → board sync, a composite action every repo with a board calls.
  It writes the labels onto the board, one way, and reads the Area options from the board itself.
- `templates/.github/`: the two short workflows that call the actions, and the skeleton of
  `tests.yml` with its lint steps and the `files` job that runs the file guide check.
- `templates/ruff.toml`, `templates/eslint.config.js` (+ `test_lint_templates.py`): the lint
  settings, following `~/.claude/rules/code-*.md`. Each repo keeps a copy; see step 3.
- `templates/README.md`: the skeleton of a repo's file guide (step 6).
- `templates/file_guide_check.py` (+ `scripts/test_file_guide_check.py`): the check that the
  file guide names every file, and only files that exist. Each repo keeps a copy; see step 6.
- `templates/netlify.toml`: the deploy-skip rule for a repo that Netlify deploys (step 3).
- `templates/ruleset-main.json` (+ `scripts/test_ruleset_template.py`): the protection of the
  default branch, a public repo's ruleset (step 5).

The issue forms are not here. They live once, in the public repo `dolev2/.github`, and GitHub
serves them to every repo of the account that has no `.github/ISSUE_TEMPLATE` of its own.

Read `reference/pipeline.md`, `reference/setup.md`, `reference/review-app.md` and
`reference/tests.md` (how the test commands in `CLAUDE.md` are read) before step 1,
so you know what each piece is for.

## Step 0: What is already there

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

`ready: True`, `missing_files: []`, `lint: []` and `netlify: []` means it is installed. Say so and stop.
Otherwise note what is missing; only that gets added. A repo that has the pipeline but a
non-empty `lint` goes through the lint parts of steps 1, 3 and 6 only. Never overwrite an existing workflow, script or
issue form: show the diff against the template and ask.

## Step 1: Agree on the setup before writing anything

Everything here writes to GitHub (labels, milestones, a board, repo settings) or to the repo.
Show Dolev, in chat, one list, and wait for his yes:

| item | default | ask about |
|---|---|---|
| repo | from `gh repo view` | — |
| `area:*` labels | `backend`, `frontend`, `both`, `infra` | fit this project? |
| milestones (sprints) | none | the names, in order; titles in English |
| Project board | a new user project named after the repo, linked to it | create one, reuse one, or skip |
| CI tests workflow | only if the repo has none | which commands |
| lint | ruff for Python, eslint for React (JavaScript), by the files in the repo | — |
| "Automatically delete head branches" | on | — |
| squash merge commit title | the PR title (`PR_TITLE`) | — |
| ruleset `protect-main` on the default branch | on, in a public repo (from a cloud session: left to Dolev, step 7); a private one is skipped | — |
| file guide in `README.md` | only if `missing_files` names it | the description line of a new `README.md` |

Without a board the pipeline still works: labels are the source of truth. Then skip step 4
and `sync-project.yml`, and keep the gate.

**The board's scheduled sync is central.** A card dragged on the board goes back to the column
of its label only through a poll every 15 minutes, and that poll runs once for every repo from the public dolev2/.github
(`sync-boards.yml`, which runs `actions/project-sync/sweep_all.py`), where Actions minutes are
free. Run in each private repo, it used up the account's 2,000 minutes (October 2026, #46).
So `sync-project.yml` here has issue events only, never a `schedule`; the central run finds a
new repo by its `PROJECT_NUMBER` variable. It also checks the number of boards it found against
the `EXPECTED_BOARDS` variable of dolev2/.github, and fails on any other number (#49), so step 4
updates that number. So does archiving a repo that has a board: the run stays red until then.

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
L "status:explore"          c5def5 "Claude חוקר וכותב תוכנית"
L "status:plan-questions"   f9d0c4 "שאלה פתוחה על התוכנית"
L "status:waiting-approval" fef2c0 "ממתין לאישור התוכנית מדולב"
L "status:ready-to-execute" 0e8a16 "מוכן לביצוע ע\"י Claude"
L "status:needs-repair"     d93f0b "חזר ל-Claude לתיקון"
L "status:in-review"        bfd4f2 "Claude סיים, בבדיקת דולב עד בקשת מיזוג"
L "status:done"             5319e7 "מוזג"
L "status:backlog"          ededed "רעיון/backlog, לא בצינור"
L "task"                    0052cc "משימה"
L "bug"                     d73a4a "באג"
L "process"                 c2e0c6 "ניהול עבודה, נהלים ויישור קו עם claude-config"
L "costs-money"             fbca04 "דורש הוצאה כספית; מושהה עד שדולב מאשר"
L "size:small"              c5def5 "משימה קטנה: עוברת לביצוע בלי אישור תוכנית"
L "has-open-questions"      d93f0b "עבר לסקירה עם שאלה שלא נסגרה"
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
- `unknown (no access from this session)`: not a place. The API cannot reach `<owner>/.github`
  from here (a cloud session). Clone it read-only (`git clone --depth 1
  https://github.com/<owner>/.github <scratchpad>/owner-github`; the git proxy serves a public
  repo without attaching it), check the repo's own `.github/ISSUE_TEMPLATE/` on disk, and decide
  by the three cases above.

Copy from `$HOME/.claude/skills/dev-setup/templates/.github/` into the repo's `.github/`,
only what is missing:

- `workflows/open-questions-gate.yml`: as is. It calls the shared action
  `dolev2/claude-config/skills/dev-setup/actions/open-questions-gate@main`; there is no script to copy.
  A repo that still has `.github/scripts/check_open_questions.py` from an older install: replace
  its workflow with the template and delete the script (show Dolev the diff first).
- `workflows/sync-project.yml`: as is, when there is a board. It calls the shared action
  `dolev2/claude-config/skills/dev-setup/actions/project-sync@main`; there is no script to copy.
  A repo that still has `.github/scripts/sync_project.py`: replace the workflow and delete the
  script. A `SYNC_MARKER` variable or a `sync-marker:` line left from an older install is
  ignored since #111; leave it.

If the repo has no CI and Dolev agreed to one, build `.github/workflows/tests.yml` from
`templates/.github/workflows/tests.yml`: the default branch, the folders, the repo's test
commands in place of each `# <...>` line, and only the jobs of the sides the repo has. Base it
on the stack actually in the repo; do not invent commands.

**Lint.** Each repo keeps its own copy of the settings, never a shared one: ruff cannot read
settings from a URL, and one shared change would turn every repo red at once (`reference/setup.md`). What `lint` from step 0 lists:

- `missing ruff.toml`: copy `templates/ruff.toml` to the root. Under its `# --- local ---`
  line add only what is this repo's own, as dotted keys (`target-version`, `extend-exclude`
  for migrations, `lint.isort.known-first-party`). Pin `ruff==0.17.2` in the requirements the
  CI installs.
- `missing <folder>/eslint.config.js`: copy `templates/eslint.config.js` next to that
  `package.json`, install the packages its header lists as `devDependencies`, and set
  `"lint": "eslint ."`. A repo that has `oxlint` drops it and its `.oxlintrc.json`.
- `differs <path>`: show Dolev the diff of the part above the `--- local ---` line against
  the template, and replace it only on his yes. Never edit the template to match a copy.
- `missing .github/workflows/tests.yml`, or `no ... step in` it: add the template's lint
  steps to the existing jobs, before the tests. An existing workflow: show the diff first.
  A repo without code (a static site) gets a `tests.yml` with the `files` job only.
- `missing .github/file_guide_check.py`, or `no file guide step in` the workflow: see "The
  file guide check" in step 6.

**Netlify.** Each Netlify deploy costs credits, so a repo's `netlify.toml` deploys only when
a site file changes (`reference/setup.md`). When `netlify` from step 0 says
`no build.ignore in netlify.toml`, show Dolev the `ignore` line from `templates/netlify.toml`
that fits the repo's `publish` (a folder of its own, or the root), and add it only on his yes.
Before the PR, run the rule on a pipeline merge and on a site change from the repo's history:
the first must exit 0 (skip), the second 1 (deploy). A repo without `netlify.toml` gets none.

In a repo with code, lint fails on what is already there. Fixing it belongs to the repo's
lint task (like charging-crm#66), not to a setup run; if the repo has none, open one with
`dev-issue` and install the settings there.

## Step 4: The Project board

```bash
OWNER=$(gh repo view --json owner --jq .owner.login)
gh project create --owner "$OWNER" --title "<Title>" --format json --jq .number
gh project link <number> --owner "$OWNER" --repo "$OWNER/<repo>"
gh project field-create <number> --owner "$OWNER" --name Area --data-type SINGLE_SELECT \
  --single-select-options "Backend,Frontend,Both,Infra"   # the agreed areas' option texts
gh variable set PROJECT_NUMBER --body <number>
```

Then update the number of boards the central run expects. Count them, never add 1: a second
run on the same repo would count it twice. The count uses Dolev's own `gh`, which sees every
repo; a token that sees too few is exactly what the number guards against.

```bash
N=$(python "$HOME/.claude/skills/dev-setup/actions/project-sync/sweep_all.py" --owner "$OWNER" --count-boards)
gh variable set EXPECTED_BOARDS --repo "$OWNER/.github" --body "$N"
```

The Area option texts follow one rule: the label suffix, capitalised; an acronym stays
upper-case, so `area:seo` is `SEO`. The sync matches labels to options by that rule, so
nothing else lists the areas.

`gh project` needs the `project` scope: if it is refused, ask Dolev to run
`gh auth refresh -s project`, and wait.

**Status is the built-in field**, so it is not created but rewritten. Its options must match
`STATUS_OPTIONS` in `dev-setup/actions/project-sync/sync_rules.py` exactly. Find its id, then replace its options:

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
gh api -X PATCH repos/{owner}/{repo} -f squash_merge_commit_title=PR_TITLE   -f squash_merge_commit_message=COMMIT_MESSAGES
```

The default title setting (`COMMIT_OR_PR_TITLE`) gives a one-commit PR its commit's title, not
the PR title; `PR_TITLE` makes `gh pr merge --squash` without `--subject` always use the PR
title (#87).

Create milestones in sprint order: the lowest number is the current sprint.

**Protect the default branch** (`reference/setup.md`): a PR for every change, no force push,
no deletion, squash only. Visibility first:

```bash
gh api repos/{owner}/{repo} --jq .visibility
```

- `private`: skip the whole step: no read, no attempt to create. A private repo on a free
  account has no rulesets; the hooks guard it. Step 7 reports it in one line; it is not a
  failure and not a task for Dolev.
- `public`, in a cloud session (`CLAUDE_CODE_REMOTE=true`): do not try; the proxy refuses
  writes to the rulesets API (a read works). Step 7 hands the step to Dolev.
- `public`, otherwise: read what is there, and create the ruleset only when it is missing:
  ```bash
  gh api repos/{owner}/{repo}/rulesets --jq '.[] | "\(.id) \(.name)"'
  gh api -X POST repos/{owner}/{repo}/rulesets \
    --input "$HOME/.claude/skills/dev-setup/templates/ruleset-main.json"
  ```
  One named `protect-main` already exists: compare it (`gh api repos/{owner}/{repo}/rulesets/<id>`)
  with the template, its `conditions`, `bypass_actors` and `rules`. Different: show Dolev the
  diff, and replace it only on his yes:
  `gh api -X PUT repos/{owner}/{repo}/rulesets/<id> --input "$HOME/.claude/skills/dev-setup/templates/ruleset-main.json"`.

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
to each next sprint by itself (`reference/setup.md`).

## Step 6: CLAUDE.md

Add a short section to the repo's `CLAUDE.md` (create the file only if Dolev agrees):

```markdown
## צינור העבודה
משימות מנוהלות כ-issues ב-<owner/repo>, עם תוויות `status:*`<, ולוח Project מס' N>.
ה-milestones הם הספרינטים. המנגנון: הסקילים `dev-issue`, `dev-next`, `dev-plan`, `dev-code`,
`dev-ship` (ב-`~/.claude/skills/`), והמסמך `dev-setup/reference/pipeline.md`.
```

Then the "הרמה לסקירה" section, in the format of `reference/review-app.md`: ask Dolev
for the command, the ports with the variable that moves each one, and the URL, or write
`אין אפליקציה.` when the repo has nothing to run. `dev-code` uses it to hand a PR over for
review with a link to the running app.

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
folder; a folder of many similar files (tests, migrations, icons) gets one row, and its pattern
goes into the check's local exceptions (below). Never leave the skeleton empty, and never
guess a file's purpose: read the file, or ask Dolev. Then add one line to `CLAUDE.md`:

```markdown
- מדריך הקבצים (מה כל קובץ ולמה הוא קיים): [README.md](README.md).
```

Also make sure it has a tests section with the exact commands, the lint commands among them
(`ruff check .`, `ruff format --check .`, `npm --prefix <folder> run lint`); `dev-code` and
`dev-ship` run whatever it says. The lint settings files get a row in the file guide. If there is none, ask Dolev for them rather than guessing.

**The file guide check.** Every repo, code or not, keeps a copy of
`templates/file_guide_check.py` at `.github/file_guide_check.py`, for the same reasons as the
lint settings (`reference/setup.md`). It fails when a file is missing from the guide, or the
guide names one that is gone or names one twice; it reads only the guide's tables (the
template's docstring says how). To install it:

1. Copy the template. Below its `# --- local ---` line, fill `COVERED_BY_PATTERN` with the
   groups the guide covers by a sentence (`backend/tests/test_*.py`, `public/*`).
2. Run `python .github/file_guide_check.py` and complete the guide until it passes. A file you
   cannot place: read it, or ask Dolev, as above.
3. Add the command to the tests section of `CLAUDE.md`, and the template's `files` job to
   `tests.yml`. The copy gets a row in the file guide. A repo with no other Python (a static
   site) gets the `files` job only, without ruff: `lint` does not count the copy as Python.
4. Add `README.md merge=union` to `.gitattributes` (claude-config #121). Most PRs add a row
   to the guide, and two of them racing would stop on a rebase conflict; union keeps both
   rows. When both sides edited the same row it keeps both versions, and the check's "twice"
   catches that. Only `README.md`: union on prose would keep two versions silently.

`differs .github/file_guide_check.py` is handled like a lint copy that differs: the diff above
the line, replaced only on Dolev's yes.

## Step 7: Verify and hand over

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

Expect `ready: True`, `missing_files: []` and `lint: []` (the sync files are allowed missing when there
is no board). The file changes are uncommitted: offer to ship them with `dev-ship`. Then tell
Dolev what is left for him: the `PROJECT_TOKEN` secret and the first issues (`dev-issue`).
A public repo set up from a cloud session adds the ruleset to that list: one line to run from
his computer, with the repo spelled out (`{owner}/{repo}` resolves only inside its folder,
and `\` does not continue a line in PowerShell),
`gh api -X POST repos/<owner>/<repo>/rulesets --input "$HOME/.claude/skills/dev-setup/templates/ruleset-main.json"`,
or by hand in Settings → Rules → Rulesets, with the
rules the template holds. A private repo gets one line instead, with nothing for him to do: the
default branch has no ruleset, because a private repo on a free account cannot have one,
and the hooks guard it.

## Golden rules

- Nothing is written to GitHub before Dolev agrees to the list in step 1.
- Never overwrite an existing workflow, script, issue form or label description silently.
- Never handle the token.
- Label names and Status option names are a contract with the scripts: exact text only.
