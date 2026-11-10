# claude-config: נהלי העבודה של דולב עם Claude

ההנחיות הגלובליות (איך Claude עונה לדולב) נמצאות ב-`CLAUDE.md` שבשורש, והכללים לכל הפרויקטים ב-`rules/`.
שינוי באופן שבו Claude עונה לדולב נכנס לשם, ולא לקובץ הזה.
הקובץ הזה הוא רק ההנחיות לעבודה על הריפו עצמו.

## מה יש כאן
הריפו הזה הוא התיקייה `~/.claude`.
ה-`.gitignore` חוסם הכל ומתיר רק את מה שמפורט בו, כי ב-`~/.claude` יש גם קבצים רגישים (`.credentials.json`, תמלולי סשנים, הזיכרון של כל פרויקט).
קובץ חדש נכנס לריפו רק אחרי שמוסיפים אותו לרשימה.
בסשן ענן, סקריפט ההתקנה של סביבת הענן הופך את `~/.claude` של ה-container לעותק של `main`. הסקריפט וההגדרה: `skills/dev-setup/reference/cloud.md`.
מדריך הקבצים (מה כל קובץ ולמה הוא קיים): [README.md](../README.md).

- `CLAUDE.md`: ההנחיות הגלובליות, שנטענות בכל פרויקט.
- `rules/`: כללים אישיים שחלים על כל הפרויקטים. נהלי הקוד: `code-general.md` ו-`code-tests.md` (נטענים תמיד), `code-python.md` ו-`code-react.md` (נטענים לפי `paths`, רק כשעובדים על קבצים מהסוג שלהם).
  נוהל קוד חדש נכנס לשם, ולא ל-`CLAUDE.md` של ריפו.
  תרשים הסכמה (ERD) של ריפו עם מסד, והבדיקה שלו: `erd.md` (נטען תמיד). התבניות שלו ב-`skills/dev-setup/templates/`.
  נהלי git (branch, rebase, התנגשות, worktree): `git.md` (נטען תמיד).
  נהלי הסביבה של המחשב (Windows, קידוד עברית, כלים זמינים, ניידות): `env-windows.md` (נטען תמיד).
  נהלי הסביבה בסשן ענן (Linux, כלים מותקנים, רשת, מה נשאר למחשב): `env-cloud.md` (נטען תמיד, חל רק בענן).
- `docs/decisions/`: דפי ההחלטות שחוצות משימות: למה הוחלט, ומה נדחה. הנוהל: `rules/code-general.md`, "ב-`docs/decisions/`".
- `docs/specs/`: האפיון של הריפו, `claude-config.md`: קובץ אחד, והנושאים פרקים בו. הפורמט, המזהים והבדיקה: `docs/specs/README.md`.
- `settings.json`: ההגדרות של Claude Code לכל הפרויקטים: כללי ההרשאות, ה-hooks ומשתני הסביבה.
- `hooks/`: הסקריפטים של ה-hooks, קובץ Python אחד לכל hook והבדיקות לצידו. כל hook מחובר ב-`settings.json` באותה צורה: `"$(command -v python3 || command -v python)" "$HOME/.claude/hooks/<name>.py"`.
  החוזה: JSON ב-stdin, יציאה 0 בלי פלט כשאין החלטה, יציאה 2 עם הסיבה ב-stderr כדי לחסום.
- `skills/`: הסקילים. הגנריים של צינור העבודה: `dev-spec`, `dev-issue`, `dev-next`, `dev-plan`, `dev-code`, `dev-ship` ו-`dev-setup`, והמתזמר של הספרינט בסשן ענן: `dev-orchestrate`.
- `.claude/CLAUDE.md`: הקובץ הזה. נטען רק כשעובדים בתוך הריפו.

`skills/dev-setup/` הוא גם הבית המשותף של הצינור: מסמכי הצינור ב-`reference/` (הליבה: `pipeline.md`), הסקריפטים `scripts/`, ה-actions המשותפים `actions/`, וה-workflows ב-`templates/.github/` שמועתקים לכל ריפו.

טפסי ה-issues לא כאן. הם גרים בריפו הציבורי [dolev2/.github](https://github.com/dolev2/.github), ומשם מגיעים לכל הריפואים.

## כללי עבודה
- **התיקייה הראשית היא הסקילים וההנחיות החיים.** כל סשן, בכל ריפו, טוען אותם ממנה.
  לכן כותבים קוד רק ב-worktree, ולא בתיקייה הראשית. שינוי מגיע אליה רק אחרי merge ו-`git pull`.
  hook ב-`hooks/guard_main_folder.py` אוכף את זה: עריכה של קובץ מהריפו בתיקייה הראשית נחסמת. מה ש-`.gitignore` מחריג (זיכרון, תוכניות) ו-`settings.json` עוברים.
- הכלל חל על כל `~/.claude`: גם שינוי ב-`CLAUDE.md` הגלובלי ובכללים עובר PR, בשביל הגיבוי וההיסטוריה.
- שינוי בתבנית ב-`skills/dev-setup/templates/` משפיע על כל ריפו חדש. ריפואים שכבר הותקנו לא מתעדכנים לבד: מציינים את זה ב-PR.
- שינוי בטופס ב-`dolev2/.github` מגיע לכל הריפואים מיד. שינוי בכותרת מחייב עדכון של מסמכי הצינור ושל הסקילים באותו זמן.
- סיומות שורה LF (`.gitattributes`).
- **שינוי בכלל של הצינור: קודם בקובץ הבעלים שלו**, לפי `skills/dev-setup/reference/owners.md`. מקום אחר מפנה אליו, ולא מעתיק.

## צינור העבודה
משימות מנוהלות כ-issues ב-[dolev2/claude-config](https://github.com/dolev2/claude-config), עם תוויות `status:*`, ולוח [Project מס' 9](https://github.com/users/dolev2/projects/9).
ה-milestones הם הספרינטים. המנגנון: הסקילים `dev-spec`, `dev-issue`, `dev-next`, `dev-plan`, `dev-code`, `dev-ship`, והמסמך `skills/dev-setup/reference/pipeline.md`.
משימות על תהליך העבודה, על הסקילים ועל ההנחיות הגלובליות נפתחות כאן, ולא בריפו של פרויקט.

תוויות האזור:
- `area:skills`: הטקסט של הסקילים (`SKILL.md`), מסמך הצינור, וההנחיות הגלובליות.
- `area:scripts`: הסקריפטים ב-`skills/dev-setup/scripts/` והבדיקות שלהם.
- `area:actions`: ה-workflows, התבניות וה-actions המשותפים.

## תרשים הצינור והעמוד "חייו של issue"
התרשים ב-`skills/dev-setup/reference/diagram.md` והעמוד "חייו של issue" מראים את הצינור לבני אדם. הסקילים לא קוראים אותם.
לעמוד שתי גרסאות, וכל אחת מפורסמת לקישור משלה:
1. בעברית: `skills/dev-setup/reference/issue-lifecycle.html`, ב-https://claude.ai/artifact/FcDGAbuAhUSpyYT34zHg1A.
2. באנגלית: `skills/dev-setup/reference/issue-lifecycle-en.html`, ב-https://claude.ai/artifact/AB2j5PLwLQvXuoUfGyVyYX.

**התרשים והעמוד הם חלק מהמנגנון, לא איור נלווה.** כל שינוי בשלבים, בתוויות, בשערים,
באוטומציות או בצעדי git מתעדכן בתרשים ובשתי הגרסאות של העמוד, באותו PR שמשנה את ההתנהגות.

**שתי הגרסאות מתארות אותו תהליך.** שינוי באחת מתורגם לשנייה באותו PR, גם כשהבקשה הייתה רק על אחת מהן.
הגרסה האנגלית באנגלית בלבד. שינוי שאי אפשר לשקף אחד לאחד (למשל תווית בתרשים שלא נכנסת): מציינים ב-PR.

**אחרי המיזוג, כל גרסה שה-PR נגע בה מפורסמת מחדש לקישור שלה**, בנתיב ובקישור שלמעלה. מי שמיזג (`dev-ship`) עושה את זה אחרי הניקוי,
בצעדים של `skills/dev-setup/reference/after-merge.md` ("פרסום מחדש של עמוד Artifact"): קריאה, השוואה לגרסה שלפני ה-PR, ו-`publish` בלי `icon` ובלי `force`.

## בדיקות
מהשורש של הריפו (או של ה-worktree). חייבות לעבור לפני PR:
```
ruff check .
ruff format --check .
python .github/file_guide_check.py
python -m pytest skills/dev-setup/scripts hooks
```
בסביבה נקייה: קודם `pip install pytest ruff==0.17.2`.
ההגדרות ב-`ruff.toml` שבשורש: עותק של `skills/dev-setup/templates/ruff.toml`, כמו בכל ריפו. שינוי בכללים נכנס לתבנית, ואז לעותק.
אותו דבר ב-`.github/file_guide_check.py`, עותק של `templates/file_guide_check.py`. החריגים של הריפו מתחת לשורת `--- local ---`.

ב-CI: `.github/workflows/tests.yml` מריץ את אותן פקודות על כל PR ועל כל push ל-`main`.

## הרמה לסקירה
אין אפליקציה.
