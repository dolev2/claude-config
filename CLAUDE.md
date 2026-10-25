# claude-skills: הסקילים האישיים של דולב

## מה יש כאן
הריפו הזה הוא התיקייה `~/.claude/skills`.

הסקילים הגנריים של צינור העבודה גרים בו: `dev-issue`, `dev-next`, `dev-plan`, `dev-code`, `dev-ship` ו-`dev-setup`.

`dev-setup/` הוא גם הבית המשותף של הצינור: המסמך `reference/pipeline.md`, הסקריפטים `scripts/`, והתבניות `templates/.github/` שמועתקות לכל ריפו.

## כללי עבודה
- **התיקייה הראשית היא הסקילים החיים.** כל סשן, בכל ריפו, טוען אותם ממנה.
  לכן כותבים קוד רק ב-worktree, ולא בתיקייה הראשית. שינוי מגיע אליה רק אחרי merge ו-`git pull`.
- שינוי בתבנית ב-`dev-setup/templates/` משפיע על כל ריפו חדש. ריפואים שכבר הותקנו לא מתעדכנים לבד: מציינים את זה ב-PR.
- סיומות שורה LF (`.gitattributes`).

## צינור העבודה
משימות מנוהלות כ-issues ב-[dolev2/claude-skills](https://github.com/dolev2/claude-skills), עם תוויות `status:*` / `owner:*`, ולוח [Project מס' 9](https://github.com/users/dolev2/projects/9).
ה-milestones הם הספרינטים. המנגנון: הסקילים `dev-issue`, `dev-next`, `dev-plan`, `dev-code`, `dev-ship`, והמסמך `dev-setup/reference/pipeline.md`.
משימות על תהליך העבודה ועל הסקילים נפתחות כאן, ולא בריפו של פרויקט.

תוויות האזור:
- `area:skills`: הטקסט של הסקילים (`SKILL.md`) ומסמך הצינור.
- `area:scripts`: הסקריפטים ב-`dev-setup/scripts/` והבדיקות שלהם.
- `area:actions`: ה-workflows, התבניות וה-actions המשותפים.

## בדיקות
מהשורש של הריפו (או של ה-worktree). חייבות לעבור לפני PR:
```
python -m pytest dev-setup/scripts
```
בסביבה נקייה: קודם `pip install pytest`.

ב-CI: `.github/workflows/tests.yml` מריץ את אותה פקודה על כל PR ועל כל push ל-`main`.
