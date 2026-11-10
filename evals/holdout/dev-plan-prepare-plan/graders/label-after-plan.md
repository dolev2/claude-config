---
type: regex
target: { source: file, path: gh-state/issues/12.labels }
pattern: '^(?![\s\S]*status:(?!waiting-approval\b|plan-questions\b))[\s\S]*status:(?:waiting-approval|plan-questions)'
---
התווית לא עברה ל-status:waiting-approval או ל-status:plan-questions.
