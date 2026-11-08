# סביבת העבודה: Windows

הכללים האלה נכונים לכל ריפו במחשב של דולב (Windows 11), חוץ מהסעיף האחרון, שמגדיר מה חייב לעבוד גם מחוצה לו.
בסשן ענן (`CLAUDE_CODE_REMOTE=true`) חל `env-cloud.md` במקומם, יחד עם הסעיף האחרון.
`CLAUDE.md` של ריפו מוסיף רק את מה שספציפי לו (גרסת Python, החבילות, נתיבי הסקריפטים שלו), ולא חוזר עליהם.

## עברית בפלט
- **`PYTHONIOENCODING=utf-8` חובה כשמריצים Python שמדפיס עברית.**
  בלי זה ה-console של Windows נופל ב-`UnicodeEncodeError` או מדפיס סימני שאלה.
  בסשן של Claude Code הוא כבר מוגדר (`env` ב-`settings.json`). מגדירים אותו ידנית רק מחוץ לסשן, למשל בטרמינל או ב-Task Scheduler.

## סקריפטי PowerShell
- **קובץ `.ps1` עם עברית נשמר כ-UTF-8 עם BOM.**
  Windows PowerShell 5.1 קורא קובץ בלי BOM בקידוד המקומי, והעברית משתבשת.
  hook מוסיף את ה-BOM אחרי Write או Edit (`hooks/ps1_bom.py`). קובץ שנכתב דרך פקודת shell לא עובר דרכו, ושם הכלל עדיין חל.
- מריצים אותו עם `powershell -ExecutionPolicy Bypass -File <script>.ps1`, כי מדיניות ברירת המחדל חוסמת סקריפטים.

## מסמכים
- **אין pandoc ואין LibreOffice.** לא מתכננים המרה שנשענת עליהם.
- **Word COM רק לקריאה.** `ExportAsFixedFormat` ו-`SaveAs2` נתקעים ולא חוזרים (לקח מ-MirrorFit).
  יצירה ועריכה של `.docx` נעשות בספריית Python.

## רינדור
- **`node` זמין**, למשל לתרשימים.
- **HTML ל-PNG דרך Edge במצב headless.** `msedge.exe` לא ב-PATH: הנתיב `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`.
  מריצים עם `--headless --disable-gpu --user-data-dir=<תיקייה זמנית> --screenshot=<out>.png <file>.html`, בנתיבים מלאים.
  בלי `--user-data-dir` נפרד, Edge שכבר פתוח בולע את הקריאה ולא נוצרת תמונה.
  **מתאים לצילום ברוחב מחשב בלבד.** `--window-size` קובע גודל חלון ולא viewport.
  ברוחב 375 העמוד מוצג רחב יותר, ונראה כאילו הוא גולל הצידה.
  רוחב טלפון נבדק בדפדפן המובנה, לפי הכלל ב-`skills/dev-setup/reference/ux.md` ("הבדיקה בקידוד").
  לכן במחשב אין צילום טלפון במסירה.
- **עמוד HTML סטטי בדפדפן המובנה:** הדפדפן לא פותח `file://`.
  1. מגישים את התיקייה ב-`python -m http.server <port> --bind 127.0.0.1 --directory <תיקייה>`, כתצורה ב-`.claude/launch.json`, ואז `preview_start`.
  2. `preview_start` קורא את `launch.json` מהתיקייה הראשית של הסשן, לא מה-worktree.
     ב-`~/.claude` הקובץ מותר, כי `.gitignore` מחריג אותו (`/.claude/*`). בריפו אחר: מוודאים שהוא לא נכנס ל-git.
  3. הוא מחזיק נתיב מוחלט, ולכן מוחקים אותו בסוף.

## מה חייב לעבוד גם מחוץ ל-Windows
- **כל מה שסוכן עלול להריץ בסביבה אחרת (CI, סשן ענן, מחשב אחר) עובד גם ב-Linux וב-macOS.**
  זה כולל את פקודות ההתקנה והבדיקה שכתובות ב-`CLAUDE.md`, ב-`README.md` וב-CI.
- **נתיב בתוך הקוד נבנה בצורה ניידת:** `pathlib` או `path.join`, ונתיב יחסי לריפו.
  לא `C:\...` ולא `\` קשיח.
- **קובץ שהוא Windows בלבד בכוונה מותר** (`.ps1`, `.cmd`, הגדרות preview עם נתיבים מוחלטים).
  הוא מסומן ככזה במדריך הקבצים של הריפו, כדי שאף אחד לא יבנה עליו פקודה שרצה במקום אחר.
