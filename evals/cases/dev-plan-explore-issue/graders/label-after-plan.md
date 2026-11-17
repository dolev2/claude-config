---
type: regex
target: { source: file, path: gh-state/issues/12.labels }
pattern: '^(?![\s\S]*status:(?!ready-to-execute\b|in-review\b|plan-questions\b))[\s\S]*status:(?:ready-to-execute|in-review|plan-questions)'
---
התווית לא עברה ל-status:ready-to-execute (או ל-status:in-review, אחרי הקוד) או ל-status:plan-questions.
