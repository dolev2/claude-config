# claude-config

נהלי העבודה של דולב עם Claude Code, במקום אחד. התיקייה הזו היא `~/.claude`.

ה-`.gitignore` חוסם הכל ומתיר רק את מה שמפורט בו. פרטי ההתחברות, התמלולים והזיכרון של הפרויקטים לא נכנסים לריפו.

ההנחיות לעבודה על הריפו עצמו: [.claude/CLAUDE.md](.claude/CLAUDE.md).

## מדריך קבצים

כל קובץ ותיקייה: מה הם ולמה הם קיימים.
מי שמוסיף קובץ שהתפקיד שלו לא מובן מאליו, או משנה את התפקיד של קובץ קיים, מעדכן את הטבלה באותו שינוי.

### השורש
| קובץ | מה הוא | למה הוא קיים |
|---|---|---|
| `CLAUDE.md` | ההנחיות הגלובליות: איך Claude עונה לדולב | נטען בכל סשן, בכל פרויקט |
| `README.md` | הקובץ הזה | מסביר מה כל קובץ |
| `.gitignore` | חוסם הכל ומתיר רק רשימה | ב-`~/.claude` יש גם פרטי התחברות, תמלולים וזיכרון. קובץ חדש נכנס לריפו רק אחרי שמוסיפים אותו לרשימה |
| `.gitattributes` | סיומות שורה LF בכל checkout | התבניות מועתקות לריפואים אחרים כמו שהן |
| `ruff.toml` | הגדרות ruff לסקריפטים של הריפו: עותק של `skills/dev-setup/templates/ruff.toml` | הריפו שמגדיר את ה-lint לכל הריפואים עומד בו בעצמו |
| `.claude/CLAUDE.md` | ההנחיות לעבודה על הריפו הזה | נטען רק בסשן שעובד בתוך הריפו |
| `.github/workflows/tests.yml` | CI: lint והבדיקות על כל PR ועל כל push ל-`main` | אותן פקודות כמו בסעיף "בדיקות" ב-`.claude/CLAUDE.md` |
| `.github/workflows/open-questions-gate.yml`, `sync-project.yml` | הצינור של הריפו הזה עצמו | המשימות של הריפו מנוהלות באותו צינור כמו כל פרויקט |

### `rules/`: כללים לכל הפרויקטים
| קובץ | מה הוא | מתי נטען |
|---|---|---|
| `code-general.md` | נהלי קוד כלליים: מודולריות, שמות, תיעוד | תמיד |
| `code-python.md` | נהלי Python: שלוש שכבות, סגנון | רק כשעובדים על קבצי Python (`paths`) |
| `code-react.md` | נהלי React | רק כשעובדים על קבצי React (`paths`) |
| `git.md` | נהלי git: מאיפה חותכים branch, rebase ואז בדיקות, התנגשות, worktree | תמיד |
| `env-windows.md` | נהלי הסביבה במחשב של דולב: Windows, קידוד עברית, כלים זמינים, ומה חייב לעבוד גם מחוץ ל-Windows | תמיד |

### `skills/`: הסקילים של צינור העבודה
| סקיל | מה עושה |
|---|---|
| `dev-issue` | פותח issues ומפרק משימות |
| `dev-next` | בוחר את המשימה הבאה בספרינט |
| `dev-plan` | שלב התכנון |
| `dev-code` | שלב הביצוע וה-merge |
| `dev-ship` | שחרור branch מההתחלה ועד הסוף |
| `dev-setup` | מתקין את הצינור בריפו חדש, ומחזיק את החלקים המשותפים (הטבלה הבאה) |

### `skills/dev-setup/`: הבית המשותף של הצינור
| קובץ | מה הוא | למה הוא קיים |
|---|---|---|
| `reference/pipeline.md` | המנגנון: תוויות, שלבים, שערים, מוקשים | המקור היחיד שכל סקילי `dev-*` מפנים אליו |
| `scripts/pipeline_info.py` | קורא מהריפו כל מה שמשתנה בין ריפואים | כל סקיל מתחיל בו, כדי ששום דבר לא יוגדר ידנית |
| `scripts/rank_issues.py` | מדרג את ה-issues בספרינט לפי כמה עבודה מחכה להם | הסדר של `dev-next`, `dev-plan` ו-`dev-code` |
| `scripts/board_views.py` | יוצר את שתי התצוגות של הלוח, "ספרינט נוכחי" ו"הכל" | התקנה של לוח בלי עבודה ידנית |
| `scripts/lint_check.py` | מדווח על הגדרות lint שחסרות בריפו, או ששונות מהתבנית | כדי שהעותקים בכל ריפו לא יסטו בשקט |
| `scripts/test_*.py` | הבדיקות של הסקריפטים ושל שני ה-actions | רצות ב-CI |
| `actions/open-questions-gate/` | שער השאלות הפתוחות, action שכל ריפו קורא לו | עותק אחד לכל הריפואים |
| `actions/project-sync/` | הסנכרון בין התוויות ללוח, action שכל ריפו עם לוח קורא לו | עותק אחד לכל הריפואים |
| `actions/project-sync/sweep_all.py` | הבדיקה המתוזמנת של כל הלוחות בבת אחת, ומדפיס רק מספרים. נכשל כשמספר הלוחות שונה מ-`EXPECTED_BOARDS` (#49) | רץ מהריפו הציבורי `dolev2/.github`, כי שם דקות ה-Actions בחינם (#46) |
| `templates/.github/workflows/` | שני ה-workflows הקצרים שקוראים ל-actions, ושלד של `tests.yml` עם צעדי lint | מועתקים לכל ריפו בהתקנה |
| `templates/ruff.toml` | הגדרות ruff ל-Python, לפי נהלי הקוד | כל ריפו עם Python מקבל עותק |
| `templates/eslint.config.js` | הגדרות eslint ל-React ב-JavaScript, לפי נהלי הקוד | כל ריפו עם React מקבל עותק |
| `templates/README.md` | שלד של מדריך קבצים | `dev-setup` יוצר ממנו מדריך בריפו שאין לו |

טפסי ה-issues לא כאן: הם בריפו הציבורי [dolev2/.github](https://github.com/dolev2/.github).

## במחשב חדש

`git clone` לא עובד לתוך `~/.claude` שכבר קיים, ולכן:

```bash
cd ~/.claude
git init -b main
git remote add origin https://github.com/dolev2/claude-config.git
git fetch origin
git reset origin/main
git branch -u origin/main
git checkout -- .
```

`git reset` מעדכן רק את ה-index, ו-`git checkout -- .` כותב את הקבצים. קבצים שכבר קיימים ב-`~/.claude` ולא בריפו לא נפגעים.

## בדיקות

```bash
python -m pytest skills/dev-setup/scripts
```
