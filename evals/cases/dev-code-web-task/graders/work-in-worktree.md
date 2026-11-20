---
type: regex
target: { source: file, path: .gitdir/logs/HEAD }
pattern: '\t(?:checkout: moving from |commit(?! \(initial\))[^:]*: (?!אפיון: דף הבית\n))'
match: "count:0"
---
הקוד נכתב בתיקייה הראשית ולא ב-worktree (S-1.68): היומן של התיקייה הראשית מראה מעבר או commit אחרי ההכנה של התרחיש.
