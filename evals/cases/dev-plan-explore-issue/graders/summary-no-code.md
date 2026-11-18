---
type: regex
target: { source: file, path: gh-state/issues/12.body.md }
pattern: '^(?![\s\S]*#### בקצרה\n)|#### בקצרה\n(?:- \*\*אפיון:?\*\*:?[^\n]*\n|(?!#)(?![^\n]*`)[^\n]*\n)*###'
---
שורה בסעיף "בקצרה" (חוץ משורת "אפיון:") מכילה קוד (גרש הפוך). השורה: בסעיף "בקצרה" של gh-state/issues/12.body.md, בתיקיית ההרצה ששמורה תחת evals/results/tmp/.
