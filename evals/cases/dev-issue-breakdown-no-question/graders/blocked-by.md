---
type: regex
target: { source: file, path: gh-state/state.json }
pattern: '"blocked_by": \[\s*1[34]\s*\]'
match: "count:1"
---
לא נוצר בדיוק קישור Blocked by אחד, לפי "תלוי ב-S-2.1" שבאפיון.
