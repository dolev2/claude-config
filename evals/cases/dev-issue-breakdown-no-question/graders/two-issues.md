---
type: regex
target: { source: file, path: gh-state/calls.jsonl }
pattern: '"(?:issue", "create"|api"[^\n]*"POST"[^\n]*/issues")[^\n]*"exit": 0'
match: "count:2"
---
לא נפתחו בדיוק שני issues, אחד לכל חלק פתוח. ייתכן שהפירוק נעצר לשאלת אישור.
