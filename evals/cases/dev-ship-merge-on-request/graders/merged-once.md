---
type: regex
target: { source: file, path: gh-state/calls.jsonl }
pattern: '"(?:pr", "merge|api"[^\n]*pulls/\d+/merge)[^\n]*"exit": 0'
match: "count:1"
---
ביקשו למזג, והמיזוג לא נקרא בדיוק פעם אחת.
