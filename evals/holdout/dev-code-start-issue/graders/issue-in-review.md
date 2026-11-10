---
type: regex
target: { source: file, path: gh-state/issues/12.labels }
pattern: '^(?![\s\S]*status:(?!in-review\b))[\s\S]*status:in-review'
---
ה-issue לא עבר ל-status:in-review, או שנשארה לו תווית status אחרת.
