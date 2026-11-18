---
type: regex
target: { source: file, path: gh-state/calls.jsonl }
pattern: '"pr", "create"[^\n]*"exit": 0'
match: "count:1"
---
לא נפתח PR אחד של שורות "פתוח".
