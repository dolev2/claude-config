---
name: dev-spec
description: Writes the spec of a topic in Dolev's pipeline as a PR — a docs/specs/<topic>.md file with a fixed id per part (S-<n>.<m>), what each part does, for whom, what the user sees in each state, and what is out — for a backlog proposal Dolev approves by asking for its spec, or for an approved task whose deliverable is a spec. The merge of that PR is the approval of the "what"; dev-issue then breaks it into issues. Use in any of Dolev's repos whenever he says "תכתוב אפיון ל-#N", "תאפיין את #N", "write a spec for #N", or asks to add parts to a topic's spec. Never merges (dev-ship does, on his request) and never runs on its own initiative. Works in any repo that has the pipeline labels; if the repo has its own repo-specific spec skill, use that instead.
---

# Write a spec

The stage before Plan in Dolev's GitHub × Claude Code pipeline: proposal → **spec** → issue →
code. This skill writes the "what" and the "why" of a topic as a file in the repo, opens it as a
PR, and stops. **No code, no Plan, no issues, and no merge here.**

## Step 0: Orient

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

- `repo_skills` lists a repo-specific spec skill? Use it instead.
- `ready` is `False`? Offer `dev-setup` and stop.
- In a cloud session (`CLAUDE_CODE_REMOTE=true`), run every `gh` command below through the table in `reference/cloud.md`.
- Note `default_branch` (written `<default>` below).

## Read first

In **`$HOME/.claude/skills/dev-setup/reference/`**: `pipeline.md` (the labels, the rules every
phase shares), `specs.md` (this stage: when it runs, the PR, the breakdown that follows),
`issue-body.md` (reading the full context of an issue), `ux.md` (the list of what a user sees),
`git-flow.md` (the working copy, the branch and PR convention) and `chat-decisions.md` (asking
Dolev in the question window); in a cloud session also `cloud.md`. Then the format of a spec
file, **`$HOME/.claude/docs/specs/README.md`**, and its skeleton,
`$HOME/.claude/skills/dev-setup/templates/spec.md`. Then the repo's **`CLAUDE.md`**: its
sources of truth, its glossary, and its rules about business data. Read them before step 1,
every run.

## Steps

1. **Check the input: one issue number, and Dolev's request for it.** Two kinds only
   (`reference/specs.md`):
   - **a backlog proposal** (`status:backlog`): his "תכתוב אפיון ל-#N" is the approval of the
     proposal. No new label: it stays `status:backlog` until the breakdown closes it;
   - **an approved task whose deliverable is a spec** (like claude-config #230):
     `status:ready-to-execute` or `status:needs-repair`, with a Plan that says so.
   Anything else stops here, with one line on why: a `bug` (it points at the part it breaks,
   and gets no new spec), a task that only needs code (`dev-plan` or `dev-code`), an issue in
   Dolev's turn. Never start on your own initiative. A proposal is never written by a child of
   the orchestrator: it has no label the orchestrator dispatches. A task like #230 is ordinary
   work: `dev-code` hands it here, also in a child session.

2. **Read the whole thread first** (`reference/issue-body.md`): body, every comment, sub-issues,
   linked PRs, and the issues it mentions. Then the code and the existing specs, against an
   up-to-date default branch and without switching branches in the shared working copy:
   ```bash
   git fetch origin <default>
   git ls-tree --name-only origin/<default> docs/specs/
   git show origin/<default>:docs/specs/<topic>.md
   ```
   Follow `CLAUDE.md` to the requirements sources, and check the open issues of the same topic,
   so a part never repeats what an open issue already owns.

3. **Pick the file.** One file per topic, `docs/specs/<topic>.md`, its name short and in English.
   - **The topic already has a file:** add parts to it. Each new part takes the next number
     never used in that file, including in its history (a number that was used never returns).
     The ids ever used in a part heading, by group (a mention such as "תלוי ב-S-1.2" is no use):
     ```bash
     git log -p --format= origin/<default> -- docs/specs/<topic>.md | grep -oE '^[+-]#{2,4} S-[0-9]+\.[0-9]+' | grep -oE 'S-[0-9]+\.[0-9]+' | sort -uV
     ```
     A new part in group `<n>` takes the highest `<m>` of that group plus one; a new group, the
     highest `<n>` plus one.
   - **A new topic:** a new file from `templates/spec.md`. The repo's first spec creates
     `docs/specs/`, and the file guide in `README.md` gets a `docs/specs/*.md` row.
   A part that is dropped gets `**מצב:** מחוץ להיקף`; it is never deleted.

4. **Write each part**, in Hebrew (or the repo's language), in the format of that README:
   - **what it does, and for whom**, in the business language and glossary of the repo;
   - **what the user sees in each state**: walk the checklist of `reference/ux.md` (the flow,
     empty, loading, error, success, a lot of data, destructive actions, phone width, language
     and direction), and write only what applies. Work with nothing a user sees says so in one
     line, and why;
   - **what is out**, and which part or issue has it;
   - **a dependency on another part**, written in the part that depends: "תלוי ב-S-1.2". The
     breakdown reads its "Blocked by" links from these lines only, so a dependency that is not
     written is not a link.
   No file, function or endpoint names, and no code: that is the "how", and it stays for the
   Plan of each issue. The parts are in the order the work should go. A new part has no status
   line: it is open.

5. **Never invent a requirement.** A price, a rule, a value or a choice nobody has made is an
   open question, not text. Collect them for the PR body's "שאלות פתוחות" section, as unticked
   boxes, each with the options you see and your recommendation. Then, when Dolev is in the
   chat, ask them in the question window (`AskUserQuestion`, `reference/chat-decisions.md`): one
   question each, at most four per call, your recommendation first with "(מומלץ)". His answer
   goes into the file, and its box is ticked with the decision. No window (an automated run):
   the PR body is where he reads them. A child session of an orchestrator never opens the
   window: it writes the questions in a comment on the issue and ends its turn.

6. **The branch**, in a worktree (in a cloud session: its own clone), never by switching
   branches in the shared working copy (`reference/git-flow.md`):
   ```bash
   git fetch origin <default>
   git push origin origin/<default>:refs/heads/claude/spec-<topic>
   ```
   Then check it out as `reference/git-flow.md` says for an issue branch, and name the session
   `<repo>: claude/spec-<topic>` (`<repo>` without the owner). A spec PR already open from an
   earlier run (a revision Dolev asked for): use its branch.

7. **Check before the push.** Commit the file (and the file-guide row, if step 3 added one),
   then:
   ```bash
   git fetch origin <default>
   git rebase origin/<default>
   python "$HOME/.claude/skills/dev-setup/scripts/spec_check.py" --toc
   python "$HOME/.claude/skills/dev-setup/scripts/spec_check.py" --no-issues
   ```
   `--toc` rewrites the file's table of contents from its headings: **every spec PR runs it**,
   since a part added or renamed without it fails the check. Commit what it changed.
   An error fails it: fix the file and run it again. Then the repo's lint and file-guide check
   (`reference/tests.md`). A conflict in the rebase: `git rebase --abort`, and stop and report.

8. **Open the PR** against `<default>`:
   ```bash
   git push -u origin claude/spec-<topic>
   gh pr create --base <default> --title "אפיון: <the topic, in words>" --body-file <file>
   ```
   In a cloud session: `mcp__github__create_pull_request`. The body, in Hebrew: the topic in one
   line, the parts it adds (id and name, one line each), the "שאלות פתוחות" section from step 5,
   and the link to the issue:
   - a proposal: `Refs #<N>`, **never `Closes`**: the proposal closes only after the breakdown;
   - a task like #230: `Closes #<N>`, like every task.
   A revision on an open PR: push to it with `git push --force-with-lease`, never a plain
   `--force`, and update the body. Then `gh pr checks <PR> --watch --fail-fast`; a red PR is not
   handed over.

9. **Hand off.** A task (the second kind) moves to Dolev's turn, with a hand-off comment as in
   `dev-code`:
   ```bash
   gh issue edit <N> --add-label "status:in-review" --remove-label "status:ready-to-execute"
   # (or --remove-label "status:needs-repair" on a repair round)
   ```
   A proposal keeps `status:backlog`; the `Refs` line already links the PR to it. Then the chat
   message, in Hebrew: the link to the PR's changes first, the parts it adds, the open questions
   left, and the next step: he reads the file in the PR, asks for fixes, and asks for the merge
   like any PR ("תמזג את ה-PR של האפיון"). **The merge is the approval of the "what".**
   When no question is left open, ask in the question window: "תמזג (מומלץ)" runs `dev-ship` on
   the PR, "אקרא ב-GitHub ואחזור" changes nothing, and "Other" with a fix revises the file on
   the same branch (step 8, a revision).

## Golden rules

- Only on Dolev's request for that issue; his "תכתוב אפיון ל-#N" is the approval of a proposal.
  A task like #230 comes from `dev-code` instead, like any approved task.
- Never merge here. The merge is `dev-ship`'s, on his request, and it is the approval.
- Never invent a requirement or business data; a gap is an open question in the PR body.
- No file, function or endpoint names in a spec: the "how" belongs to the Plan.
- A part's id never changes and a used number never returns; a dropped part is marked
  "מחוץ להיקף", never deleted.
- A dependency between parts is written in the spec, never guessed later.
- A proposal's PR says `Refs #N`, never `Closes`.
- No issues are opened here: the breakdown is `dev-issue`'s, after the merge.
