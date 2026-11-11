---
type: regex
target: { source: file, path: gh-state/issues/12.labels }
pattern: '^(?![\s\S]*status:(?!backlog\b))[\s\S]*status:backlog'
---
השער לא החזיר את #12 ל-status:backlog, או שנשארה לו תווית מצב אחרת.
