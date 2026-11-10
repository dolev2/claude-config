---
type: regex
target: { source: file, path: gh-state/issues/12.labels }
pattern: '^(?![\s\S]*status:(?!done\b))[\s\S]*status:done'
---
ה-issue לא עבר ל-status:done, או שנשארה לו תווית status אחרת.
