---
name: status
description: Shows the work in the current repo at a glance, in four tables — the five issues merged last, the open issues of the current sprint, the issues that are blocked or cost money, and what waits for Dolev — and a Mermaid graph of the sprint's blocking order with each issue's status, by running one script and printing its output as it is, and republishes the same graph as the repo's clickable page, where each node links to its issue, open PR and session. Read-only on GitHub. Use in any of Dolev's repos whenever he types "/status", "סטטוס", "מה המצב", "תן לי סקירה", or asks for an overview of the work. Not for picking the next issue: that is dev-next.
---

# Status

A view of the spec parts S-1.41, S-1.48 and S-1.50 (`docs/specs/claude-config.md`). The
script holds all the logic; this skill reads the sessions, runs it, publishes the page it
wrote, and shows what it printed.

## Step 1: Read the sessions

`mcp__claude-code-remote__list_sessions` with `tags: ["repo:<owner>/<name>"]` (the repo
of the current directory) and `limit: 100`; drop the archived ones. For each session that
has an `issue:<N>` tag, one entry under `"<N>"`: `{"url":
"https://claude.ai/code/<session id>", "title": ..., "created_at": ...}`. Write them, as
JSON, to `<scratchpad>/status-sessions.json`. The tool is missing, or the call fails: skip
`--sessions` in step 2; the page then says the sessions were not read.

## Step 2: Run the script

```bash
python "$HOME/.claude/skills/dev-setup/scripts/work_status.py" --page <scratchpad>/status-page.html --sessions <scratchpad>/status-sessions.json
```

## Step 3: Publish the page

Only when the script wrote the page (exit 0 with the tables). The page's name is fixed per
repo: `גרף החסימות · <name>` (`<name>` without the owner).
1. `Artifact` `action: "list"` with `limit: 200`, and find the row with exactly that title.
2. Found: `read` it, then `publish` the file with `url` set to it, with no `icon` and no
   `force`. Not found: `publish` it as a new page, with `icon: "chart"`.
3. The publish failed or was declined: the link line of step 4 says the page was not
   updated, and why, in one line.

## Step 4: Show the output

Print the script's output exactly as it is: five headings, the four tables (each with its
rows or the line "אין.") and the blocking graph (a `mermaid` block, or one line saying why
there is none). Do not rebuild, reorder, filter or summarize the rows, and keep the
`mermaid` block as it is: the app draws it, and the terminal shows it as text. Add nothing
between the sections. Under the graph, one line: `הגרף הלחיץ: [גרף החסימות · <name>](<url>)`,
or the line of step 3.

- **Exit 0 with one sentence** (the repo has no pipeline): show the sentence, and offer
  `dev-setup`. No page.
- **Exit 1** (GitHub did not answer): show the message as it is. Never show tables from an
  earlier run, or build them yourself. No page: the one already published stays as it was.
- **Exit 2** (the sessions file is broken): fix the file, or run again without
  `--sessions`.

Then end with "מה פתוח", as every answer does (global `CLAUDE.md`). When the tables leave the
next step clear, recommend it there: an issue waiting for Dolev first, otherwise what
`dev-next` would pick.

## Golden rules

- Read only on GitHub: no label, issue, branch or PR changes here. The page is the only
  thing it writes.
- The tables and the graph are the script's; never edit their content, or the page's.
