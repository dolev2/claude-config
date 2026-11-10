---
type: regex
target: { source: file, path: gh-state/calls.jsonl }
pattern: '"(?:pr", "merge|api"[^\n]*pulls/\d+/merge)'
match: "count:0"
---
נקרא מיזוג בלי בקשה.
