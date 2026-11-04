# git בצינור: כמה issues בריצה, עותק העבודה, branches ו-PR

הכללים הכלליים (חיתוך מ-`origin/<default>`, קודם rebase ואז הבדיקות, rebase ולא merge,
`--force-with-lease`, התנגשות היא עצירה, לא מחליפים branch בתיקייה המשותפת) ב-`~/.claude/rules/git.md`.
כאן רק מה שהצינור מוסיף עליהם.

## כמה issues בריצה אחת, ומתי בכלל לא להתחיל

**Execute: issue אחד בדיוק בכל ריצה.** לסשן יש עותק עבודה אחד; issue שני בריצה פירושו שהקומיטים
שלו נוחתים על ה-branch של הקודם, וה-PR שלו נושא בשקט קוד לא קשור. וכל issue נוסף נכתב בקונטקסט
דחוס, באיכות נמוכה יותר.

**שער WIP:** לפני issue **חדש** (לא תיקון), כששלושה ומעלה ב-`status:in-review`, **לא מתחילים בלי
לשאול.** מדווחים כמה ממתינים (עם קישורים) ושואלים את דולב אם להמשיך בכל זאת; ממשיכים רק על "כן"
מפורש. החסם הוא קצב הביקורת של דולב, ו-PR שממתין מזדקן מול ה-branch הראשי. `status:needs-repair`
פטור מהשאלה. הפקודה ב-`dev-code`, שלב 1.

**Plan: עד שלושה issues בריצה.** הוא לא כותב קוד, אז רק הקונטקסט מגביל אותו.

## עותק העבודה בכל שלב

- **Plan לא עושה checkout בכלל.** הוא יוצר את ה-branch ישירות ב-remote וקורא את הקוד העדכני
  משם:
  ```bash
  git fetch origin <default>
  git push origin origin/<default>:refs/heads/claude/issue-<N>-<slug>   # ה-branch נוצר ב-GitHub
  git show origin/<default>:path/to/file                                 # קריאת קובץ עדכני
  git grep <pattern> origin/<default> -- <path>                          # חיפוש בקוד העדכני
  ```
  כשהתיקייה עצמה נקייה, על `<default>` ומעודכנת (`git status -sb` מראה שאין פיגור), אפשר לקרוא
  ממנה ישירות.
- **Code עובד ב-worktree**, תיקייה נפרדת עם ה-branch שלו. אם הסשן כבר רץ ב-worktree משלו (Claude
  Desktop פותח כך סשנים; `git rev-parse --git-dir` מכיל `/worktrees/`), עובדים בו. אחרת: כלי
  `EnterWorktree` אם הוא זמין, ואם לא:
  ```bash
  git fetch origin claude/issue-<N>-<slug>
  git worktree add "<parent of repo>/worktrees/<repo>-issue-<N>" -B claude/issue-<N>-<slug> origin/claude/issue-<N>-<slug>
  ```
  ומשם כל פקודה רצה בתיקייה הזו (נתיב מלא או `git -C <path>`), כי ה-shell עלול לחזור לתיקייה
  הראשית בין פקודות.
- **סוכנים בעבודה במקביל** מקבלים כל אחד worktree זמני משלו, מהכלי `Agent` עם
  `isolation: "worktree"`. הם עושים commit בעותק שלהם ולא דוחפים. הסשן הראשי מעביר את ה-commits
  ל-branch של המשימה ב-`cherry-pick`, ואז מוחק את העותקים ואת ה-branches המקומיים הזמניים שלהם.
  אלה אף פעם לא מגיעים ל-GitHub. קובץ החלקים, ההרשמה וה-hook `hooks/guard_parallel_parts.py`:
  `dev-code`, שלב 5. ה-hook חוסם כתיבה בלבד, קריאה מכל עותק מותרת.
- **בסוף ריצת Code, ה-worktree נשאר.** האפליקציה לסקירה רצה ממנו (`review-app.md`), וסבב
  תיקון ממשיך בו. הוא נמחק ב-merge (`dev-code` Part B, או `dev-ship`): קודם עוצרים את האפליקציה,
  ואז `git worktree remove <path>`. הפקודה מסרבת כשיש בו שינויים, וזה המצב שבו עוצרים ומדווחים.
- **אם בכל זאת עובדים בתיקייה המשותפת** (דולב ביקש במפורש), כלל העץ הנקי של `rules/git.md` חל בין
  issue ל-issue, לפני כל `git checkout <default>`.

## מוסכמת branches ו-PR

- branch: `claude/issue-<N>-<slug-אנגלי-קצר>`. גם `dev-ship` משתמש בשם הזה כשהעבודה שייכת ל-issue.
- הקישור ל-issue נוצר דרך `Closes #<N>` בגוף ה-PR.
- שם הסשן: `/rename claude/issue-<N>-<slug>` כשמתחילים לעבוד על ה-branch.
- מחיקת branches אחרי merge: ההגדרה "Automatically delete head branches" של ה-repo.

## עדכון מול ה-branch הראשי, ו-CI לפני merge

ה-branch הראשי זז בזמן שכותבים: כמה סשנים ו-worktrees עובדים במקביל, ושלב התכנון פותח את
ה-branch יום או יותר לפני הקוד. לכן כל שלב שמגיע ל-PR עושה `git fetch origin <default>` ו-
`git rebase origin/<default>` לפני הבדיקות.

- **התנגשות בשלב Code:** `git rebase --abort`, הסטטוס נשאר כמו שהוא, תגובה ב-issue עם רשימת
  הקבצים, ואין PR.
- **בשלב ה-Merge:** `gh pr view <N> --json mergeable,mergeStateStatus`. כל תשובה שאינה `MERGEABLE`:
  rebase, דחיפה, בדיקות מחדש, ורק אז merge.
- **לפני כל merge, גם ה-CI**, אם יש ב-repo workflow שרץ על PR. ב-repo פרטי בחשבון חינמי אין branch
  protection, ו-PR אדום ניתן ל-merge. לכן מחכים: `gh pr checks <N> --watch --fail-fast`.
  אין checks בכלל (`no checks reported`): לציין את זה בדיווח, ולהמשיך על סמך הבדיקות המקומיות.
