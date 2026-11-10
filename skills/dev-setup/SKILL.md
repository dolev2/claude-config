---
name: dev-setup
description: Installs Dolev's GitHub × Claude Code issue pipeline in the current repo — the status:/area: labels, a check that the shared task and bug issue forms reach the repo, the label→board sync workflow, the open-questions gate, sprint milestones, a linked Project board, and a pointer in CLAUDE.md — so that dev-issue, dev-next, dev-spec, dev-plan, dev-code and dev-ship work there — and moves a repo installed before the spec-first order onto it. Use whenever Dolev asks to set up, install, bootstrap or add "the pipeline" / "הצינור" / "the workflow from CRM" to a repo, starts a new project and wants the same flow, or when another dev-* skill reports the pipeline is missing. Also holds the shared reference files and scripts the other dev-* skills use.
---

# Set up the pipeline in a repo

This skill folder is also the shared home of the pipeline: the mechanism every dev-* skill
follows (`reference/`, with `pipeline.md` as its core), the scripts, the shared actions and the
templates. What each file is, and why it exists: the file guide in the repo's `README.md`.

Read `reference/pipeline.md`, `reference/setup.md`, `reference/review-app.md` and
`reference/tests.md` (how the test commands in `CLAUDE.md` are read) before step 1,
so you know what each piece is for. `reference/board.md` (steps 4–5) and
`reference/repo-files.md` (steps 3 and 6) hold the details of those steps, and
`reference/specs.md` the move to the spec-first order (step 8).

## Step 0: What is already there

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

`ready: True`, `missing_files: []`, `lint: []` and `netlify: []` means it is installed: only
step 8 (the spec-first order) may be left. Check it there, and otherwise say so and stop.
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

**The board's scheduled sync is central**, run once for every repo from dolev2/.github, so
`sync-project.yml` here has issue events only, and step 4 updates `EXPECTED_BOARDS`
(`reference/board.md`).

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

**Lint and Netlify**, by what step 0 listed; the details of each item are in
`reference/repo-files.md`:

- `lint`, `missing ...`: copy the template, add only this repo's own settings under its
  `--- local ---` line, and wire it into `tests.yml`.
- `lint`, `differs <path>`: show Dolev the diff above the `--- local ---` line, and replace
  it only on his yes. Never edit the template to match a copy.
- `netlify`, `no build.ignore in netlify.toml`: add the template's `ignore` line only on his
  yes, after running it on the repo's history.

In a repo with code, lint fails on what is already there: fixing it is the repo's lint task,
not a setup run.

## Step 4: The Project board

Follow `reference/board.md`, in this order:

1. Create the board, link it to the repo, add the Area field, and set `PROJECT_NUMBER`.
2. Count the boards and set `EXPECTED_BOARDS` on dolev2/.github; never add 1.
3. Rewrite the built-in Status field so its options match `STATUS_OPTIONS` exactly.
4. Give Dolev the `PROJECT_TOKEN` command, in both versions (PowerShell and bash), to run
   himself. **The token is his step, never yours**: never ask him to paste it into the chat.

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

The gate workflow resolves its action from `dolev2/claude-config`, which is public, so the
action reaches every repo, private or public, with no access setting. Check that it still is:

```bash
gh api repos/dolev2/claude-config --jq .visibility   # expect: public
```

Private: tell Dolev. Then every gate run fails on "Unable to resolve action".

With a board, give it its views now that the milestones exist: `board_views.py`, as
`reference/board.md` says.

## Step 6: CLAUDE.md

Add a short section to the repo's `CLAUDE.md` (create the file only if Dolev agrees):

```markdown
## צינור העבודה
משימות מנוהלות כ-issues ב-<owner/repo>, עם תוויות `status:*`<, ולוח Project מס' N>.
ה-milestones הם הספרינטים. המנגנון: הסקילים `dev-issue`, `dev-next`, `dev-plan`, `dev-code`,
`dev-ship`, ולפניהם `dev-spec` לאפיון (ב-`~/.claude/skills/`), והמסמך `dev-setup/reference/pipeline.md`.
האפיונים ב-`docs/specs/`.
```

Then the "הרמה לסקירה" section, in the format of `reference/review-app.md`: ask Dolev
for the command, the ports with the variable that moves each one, and the URL, or write
`אין אפליקציה.` when the repo has nothing to run. `dev-code` uses it to hand a PR over for
review with a link to the running app.

Keep `CLAUDE.md` to what is specific to this repo: where its layers and shared components
live, where its design tokens come from, its glossary, its commands. The code rules in
`~/.claude/rules/` load in every session, so a rule already written there is not repeated
here; if the file already repeats one, point it out to Dolev rather than deleting it.

Also make sure it has a tests section with the exact commands, the lint commands among them
(`ruff check .`, `ruff format --check .`, `npm --prefix <folder> run lint`);
`dev-code` and `dev-ship` run whatever it says. If there is none, ask Dolev rather than guessing.

**The file guide and its check** (`~/.claude/rules/code-general.md`), when `missing_files`
names `README.md (file guide)` or `lint` names the check: follow `reference/repo-files.md`.
Fill the guide from the files actually in the repo, never guess a file's purpose, install the
copy of `file_guide_check.py` with the `files` job, and add `README.md merge=union` to
`.gitattributes`. Then add the guide's pointer line to `CLAUDE.md`.

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

## Step 8: Move to the spec-first order (a repo installed before it)

The order is proposal → spec → issue → code (`reference/specs.md`). A repo installed before it
is found by either sign:

```bash
grep -n "spec-check" .github/workflows/tests.yml
python "$HOME/.claude/skills/dev-setup/scripts/spec_check.py"
```

No `spec-check` step in `tests.yml`, warnings that an open issue has no spec line, or the
warning "N spec files" (a repo from before one spec per repo, #242). Then, as
in every step here, **propose and wait for Dolev's yes**; the details are in
`reference/specs.md`, "ריפו שהותקן לפני הסדר החדש":
1. the `spec-check` step from the template's `tests.yml` (with `issues: read`), shown as a diff;
2. the open topics, one line each, each to get its chapter in the repo's one spec,
   `docs/specs/<repo>.md`, through `dev-spec`, one PR per topic, on his request for each;
3. once a topic's spec is merged, a spec line in every open issue of it that is not in the
   backlog, listed for him before any body is edited;
4. **several spec files** ("N spec files"): merged into `docs/specs/<repo>.md` in one `dev-spec`
   run and one PR, only on his request. Each topic becomes a chapter, so its ids take the
   chapter's number; each open part gets its `**מצב:** פתוח (#N)` line and each part marked
   "מחוץ להיקף" is deleted, in the same PR. After the merge, the spec line of every open issue
   moves to the new ids, from a list (issue, old line, new line) shown to him first.
The backlog stays as it is. The move is done when `spec_check.py` warns about no issue without
a spec line and about no second spec file; until then, step 7 lists what is left.

## Golden rules

- Nothing is written to GitHub before Dolev agrees to the list in step 1.
- Never overwrite an existing workflow, script, issue form or label description silently.
- Never handle the token.
- Label names and Status option names are a contract with the scripts: exact text only.
