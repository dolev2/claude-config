# סביבת העבודה: Windows

הכללים האלה נכונים לכל ריפו במחשב של דולב (Windows 11).
`CLAUDE.md` של ריפו מוסיף רק את מה שספציפי לו (גרסת Python, החבילות, נתיבי הסקריפטים שלו), ולא חוזר עליהם.

## עברית בפלט
- **`PYTHONIOENCODING=utf-8` חובה כשמריצים Python שמדפיס עברית.**
  בלי זה ה-console של Windows נופל ב-`UnicodeEncodeError` או מדפיס סימני שאלה.

## סקריפטי PowerShell
- **קובץ `.ps1` עם עברית נשמר כ-UTF-8 עם BOM.**
  Windows PowerShell 5.1 קורא קובץ בלי BOM בקידוד המקומי, והעברית משתבשת.
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
