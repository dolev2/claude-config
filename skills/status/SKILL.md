---
name: status
description: Shows the work in the current repo at a glance, in four tables — the five issues merged last, the open issues of the current sprint, the issues that are blocked or cost money, and what waits for Dolev — by running one script and printing its output as it is. Read-only. Use in any of Dolev's repos whenever he types "/status", "סטטוס", "מה המצב", "תן לי סקירה", or asks for an overview of the work. Not for picking the next issue: that is dev-next.
---

# Status

A read-only view of the spec part S-1.41 (`docs/specs/claude-config.md`). The script holds
all the logic; this skill only runs it and shows what it printed.

## Step 1: Run the script

```bash
python "$HOME/.claude/skills/dev-setup/scripts/work_status.py"
```

## Step 2: Show the output

Print the script's output exactly as it is: four headings, each with its table or the line
"אין.". Do not rebuild, reorder, filter or summarize the rows. Add nothing between the tables.

- **Exit 0 with one sentence** (the repo has no pipeline): show the sentence, and offer
  `dev-setup`.
- **Exit 1** (GitHub did not answer): show the message as it is. Never show tables from an
  earlier run, or build them yourself.

Then end with "מה פתוח", as every answer does (global `CLAUDE.md`). When the tables leave the
next step clear, recommend it there: an issue waiting for Dolev first, otherwise what
`dev-next` would pick.

## Golden rules

- Read only: no label, issue, branch or PR changes here.
- The tables are the script's; never edit their content.
