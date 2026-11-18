---
type: regex
target: { source: file, path: gh-state/calls.jsonl }
pattern: '"api"(?![^\n]*"GET")(?=[^\n]*/milestones")(?=[^\n]*"(?:-f|-F|--field|--raw-field|--input)")[^\n]*"exit": 0'
match: "count:1"
---
לא נפתח milestone חדש אחד בשם הנושא, אף שאין milestone קיים שמתאים לחלקים.
