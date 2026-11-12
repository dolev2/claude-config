---
name: status
description: Shows the work in the current repo at a glance, in four tables — the five issues merged last, the open issues of the current sprint, the issues that are blocked or cost money, and what waits for Dolev — and a Mermaid graph of the sprint's blocking order with each issue's status, by running one script and printing its output as it is. Read-only. Use in any of Dolev's repos whenever he types "/status", "סטטוס", "מה המצב", "תן לי סקירה", or asks for an overview of the work. Not for picking the next issue: that is dev-next.
---

# Status

A read-only view of the spec parts S-1.41 and S-1.48 (`docs/specs/claude-config.md`). The script holds
all the logic; this skill only runs it and shows what it printed.

## Step 1: Run the script

```bash
python "$HOME/.claude/skills/dev-setup/scripts/work_status.py"
```

## Step 2: Show the output

Print the script's output exactly as it is: five headings, the four tables (each with its
rows or the line "אין.") and the blocking graph (a `mermaid` block, or one line saying why
there is none). Do not rebuild, reorder, filter or summarize the rows, and keep the
`mermaid` block as it is: the app draws it, and the terminal shows it as text. Add nothing
between the sections.

- **Exit 0 with one sentence** (the repo has no pipeline): show the sentence, and offer
  `dev-setup`.
- **Exit 1** (GitHub did not answer): show the message as it is. Never show tables from an
  earlier run, or build them yourself.

Then end with "מה פתוח", as every answer does (global `CLAUDE.md`). When the tables leave the
next step clear, recommend it there: an issue waiting for Dolev first, otherwise what
`dev-next` would pick.

## Golden rules

- Read only: no label, issue, branch or PR changes here.
- The tables and the graph are the script's; never edit their content.
