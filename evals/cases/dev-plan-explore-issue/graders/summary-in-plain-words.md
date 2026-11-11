---
type: llm
focus: { source: file, path: gh-state/issues/12.body.md }
---
הסעיף "בקצרה" בתוכנית לא כתוב במילים פשוטות, או שהוא חסר.

PASS if the issue body has a "#### בקצרה" subsection under "### Plan" whose lines describe the change in plain Hebrew for a non-programmer, with no file names, file paths, function names or code (the spec reference line with docs/specs/demo.md and S-1.1 is allowed).
FAIL if there is no such subsection, or if any other line in it names a file, a path, a function or code.
