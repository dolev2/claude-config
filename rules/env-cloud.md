# סביבת העבודה: סשן ענן

הכללים האלה חלים רק בסשן ענן של Claude Code. מזהים אותו לפי `CLAUDE_CODE_REMOTE=true` בסביבה.
במחשב של דולב חל `env-windows.md`. הסעיף שלו "מה חייב לעבוד גם מחוץ ל-Windows" חל על שתי הסביבות.
ההגדרה של סביבת הענן, והטבלה של פקודות GitHub: `skills/dev-setup/reference/cloud.md`.

## המחשב
- **Linux, בלי PowerShell.** כללי ה-PowerShell, Edge ו-Word COM של `env-windows.md` לא חלים כאן.
- **פלט Python בעברית עובד בלי הגדרה:** הקידוד הוא UTF-8 כברירת מחדל.
- **מותקנים** (נבדק ב-6.11.2026):
  1. `node`.
  2. pandoc ו-LibreOffice (`soffice`). מותר להשתמש בהם בענן, אבל לא בקוד שאמור לרוץ גם במחשב.
  3. Chromium עם Playwright: `require('playwright')` עובד מכל תיקייה. לא מריצים `playwright install`.
- **ה-container זמני.** מה שלא נדחף ל-GitHub אובד כשהסשן נגמר.

## רשת ו-GitHub
- **הרשת עוברת דרך proxy.** אתר שלא ברשימה של הסביבה חסום.
- **GitHub רק ב-REST** (`gh api`) ובכלי `mcp__github__*`. GraphQL חסום, ולכן `gh issue` ו-`gh pr` לא רצים. התרגום: הטבלה ב-`cloud.md`.
- **`git push` שמוחק branch חסום.** ה-branch נמחק בהגדרה של הריפו אחרי המיזוג (`git-flow.md`, "בסשן ענן").

## בדיקה ויזואלית ואפליקציה לסקירה
- **צילום מסך:** Playwright במצב headless, במקום Edge או הדפדפן המובנה. הצעדים: `skills/dev-setup/reference/ux.md`.
- **אפליקציה לסקירה:** עולה בתוך ה-container, והפורט נמסר ב-`report_preview_port` (`review-app.md`).
- **מה נשאר למחשב:** פקודה או כלי של Windows בלבד (`.ps1`, `.cmd`), ושירות שהרשת של הסביבה חוסמת. מציינים את זה במסירה.
