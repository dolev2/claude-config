# נהלי git

הכללים האלה חלים על כל ריפו, גם כשאף סקיל `dev-*` לא רץ.
`<default>` הוא ה-branch הראשי של הריפו (`main` או `master`).
הפקודות המלאות של שלבי הצינור (יצירת branch ב-remote בתכנון, worktree בביצוע) כתובות ב-`skills/dev-setup/reference/git-flow.md`.

## מאיפה מתחילים
- **branch נחתך מ-`origin/<default>` אחרי `git fetch`**, לא מה-branch המקומי.
  כמה סשנים עובדים על אותו ריפו במקביל, וה-branch המקומי יכול להיות כמה merges מאחור.

## לפני push או PR
- **קודם `git fetch origin <default>` ו-`git rebase origin/<default>`, ואז הבדיקות.**
  הסדר הזה תופס התנגשות סמויה: שני שינויים שמתמזגים בלי התנגשות בטקסט, אבל יחד הקוד שבור.
- **rebase ולא merge.** ההיסטוריה לינארית, וה-PRים נסגרים ב-squash.
- **branch שכבר נדחף מתעדכן ב-`git push --force-with-lease`**, לעולם לא `--force`.
  `--force` דורס בשקט commits שמישהו אחר דחף בינתיים.
  hook ב-`~/.claude/hooks/block_force_push.py` חוסם את `--force`, `-f` ו-refspec עם `+`.
- **merge של PR רק באישור מפורש של דולב.** חלון אישור קופץ לפני כל מיזוג, בכל דרך:
  1. `gh pr merge`: כלל `ask` ב-`~/.claude/settings.json`.
  2. כל דרך אחרת (`gh api ... pulls/<N>/merge`, GraphQL, וכלי ה-MCP של GitHub, כולל מיזוג אוטומטי): hook ב-`~/.claude/hooks/ask_before_merge.py`.
  דולב דחה את החלון: עוצרים ומדווחים, ולא ממזגים בדרך אחרת.
- **התנגשות היא עצירה ושאלה, לא משימה.** `git rebase --abort`, ודיווח על הקבצים שמתנגשים.
  לא פותרים אותה בלקיחת צד אחד בשלמותו.

## התיקייה המשותפת
- **לא מחליפים branch בתיקייה הראשית של ריפו.** דולב או סשן אחר עלולים לעבוד בה, עם שינויים שלא נשמרו,
  ו-`git checkout` גורר אותם בשקט ל-branch הלא נכון. עובדים ב-worktree.
  בתיקייה הראשית של `~/.claude` זה נאכף: hook ב-`~/.claude/hooks/guard_main_folder.py` חוסם שם `git checkout` ו-`git switch`.
- אם בכל זאת חייבים: רק כש-`git status --porcelain` ריק (`git diff` לא רואה קבצים חדשים).
  פלט לא ריק: עוצרים ומדווחים, לא מנקים.
- **חריג: סשן ענן** (`CLAUDE_CODE_REMOTE=true`). ה-clone שלו לא משותף, ולכן מחליפים בו branch ישירות, באותו תנאי של עץ נקי. לא ב-`~/.claude`, שם ה-hook חוסם גם בענן (`skills/dev-setup/reference/git-flow.md`, "בסשן ענן").
