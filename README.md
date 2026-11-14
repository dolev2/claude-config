# claude-config

נהלי העבודה של דולב עם Claude Code, במקום אחד. התיקייה הזו היא `~/.claude`.

ה-`.gitignore` חוסם הכל ומתיר רק את מה שמפורט בו. פרטי ההתחברות, התמלולים והזיכרון של הפרויקטים לא נכנסים לריפו.

ההנחיות לעבודה על הריפו עצמו: [.claude/CLAUDE.md](.claude/CLAUDE.md).

## מדריך קבצים

ה-README הזה מראה את מבנה התיקיות, ומתאר רק את הקבצים שבשורש, ב-`.github/`, ב-`.claude/` וב-`rules/`.
לכל תיקייה אחרת יש README משלה, שמסביר את הקבצים שבה ואת תתי-התיקיות שלה, משפט לכל קובץ.
מי שמוסיף קובץ, או משנה את התפקיד של קובץ קיים, מעדכן את ה-README הקרוב אליו באותו שינוי.
הבדיקה `.github/file_guide_check.py` נכשלת על קובץ שה-README הקרוב אליו לא מתאר.

### מבנה התיקיות
| תיקייה | מה היא | פרק באפיון |
|---|---|---|
| `rules/` | הכללים שחלים על כל הפרויקטים, ונטענים לבד לכל סשן | פרק 4, הכללים |
| `hooks/` | השומרים: סקריפטים ש-Claude Code מריץ לפני פעולה או אחריה ([README](hooks/README.md)) | פרק 3, השומרים |
| `skills/` | הסקילים של צינור העבודה, והבית המשותף שלהם ב-`dev-setup/` ([README](skills/README.md)) | פרק 1, צינור העבודה, ופרק 2, המתזמר |
| `evals/` | תרחישי הסקילים: מריצים כל סקיל מול GitHub מדומה ובודקים מה הוא עשה ([README](evals/README.md)) | פרק 1, הידע על הצינור |
| `docs/` | האפיון של הריפו, דפי ההחלטות והרטרו ([README](docs/README.md)) | פרק 1 (האפיון) ופרק 4 (ההחלטות) |
| `.github/` | ה-CI של הריפו והבדיקות שהוא מריץ (מתוארים למטה) | פרק 4, נהלי הקוד |
| `.claude/` | ההנחיות לעבודה על הריפו עצמו (מתוארות למטה) | פרק 4, הכללים |

### השורש
| קובץ | מה הוא |
|---|---|
| `CLAUDE.md` | ההנחיות הגלובליות: איך Claude עונה לדולב, בכל סשן ובכל פרויקט. |
| `README.md` | הקובץ הזה: מבנה התיקיות, וקבצי השורש. |
| `.gitignore` | חוסם הכל ומתיר רק רשימה, כי ב-`~/.claude` יש גם פרטי התחברות, תמלולים וזיכרון. |
| `.gitattributes` | סיומות שורה LF בכל checkout, ומיזוג union לכל README, כדי ששתי שורות חדשות לא יתנגשו. |
| `ruff.toml` | הגדרות ruff של הריפו, עותק של התבנית ב-`skills/dev-setup/templates/`. |
| `settings.json` | ההגדרות של Claude Code לכל הפרויקטים: הרשאות, hooks ומשתני סביבה. |
| `.claude/CLAUDE.md` | ההנחיות לעבודה על הריפו הזה, שנטענות רק בסשן שעובד בתוכו. |
| `.github/workflows/tests.yml` | ה-CI: ה-lint והבדיקות על כל PR ועל כל push ל-`main`. |
| `.github/workflows/open-questions-gate.yml`, `sync-project.yml` | שער השאלות והסנכרון ללוח, כי המשימות של הריפו עוברות באותו צינור כמו כל פרויקט. |
| `.github/file_guide_check.py` | בודק שכל קובץ מתואר ב-README הקרוב אליו: עותק של התבנית, עם החריגים של הריפו מתחת ל-`--- local ---`. |
| `.github/holdout_check.py` | נכשל כש-PR משנה גם סקיל וגם את `evals/holdout/`, כדי שהסט השמור יישאר מדד אמיתי. |

### `rules/`: כללים לכל הפרויקטים
אין לתיקייה README משלה: כל קובץ בה נטען לבד לכל סשן, ו-README היה נטען איתם.

| קובץ | מה הוא |
|---|---|
| `code-general.md` | נהלי הקוד הכלליים, מודולריות, שמות ותיעוד, שנטענים תמיד. |
| `code-tests.md` | נהלי הבדיקות, מה בודקים לפי סוג השינוי, שנטענים תמיד. |
| `code-python.md` | נהלי Python, שנטענים רק כשעובדים על קבצי Python. |
| `code-react.md` | נהלי React, שנטענים רק כשעובדים על קבצי React. |
| `git.md` | נהלי git, מאיפה חותכים branch, rebase, התנגשות ו-worktree, שנטענים תמיד. |
| `erd.md` | נוהל תרשים הסכמה של ריפו עם מסד והבדיקה שלו, שנטען תמיד כי הוא חל כבר בתכנון. |
| `env-windows.md` | נהלי הסביבה במחשב של דולב ומה חייב לעבוד גם מחוץ ל-Windows, שנטענים תמיד. |
| `env-cloud.md` | נהלי הסביבה בסשן ענן, שחלים רק כש-`CLAUDE_CODE_REMOTE=true`. |

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

`settings.json` כן בריפו, ולכן `git checkout -- .` דורס את הקובץ שהיה במחשב. הגדרות שרק המחשב הזה צריך נכנסות ל-`settings.local.json`, שנשאר מחוץ לריפו.

## בדיקות

מהשורש של הריפו. אותן פקודות כמו ב-`.claude/CLAUDE.md`, בכוונה (`skills/dev-setup/reference/owners.md`):
```bash
ruff check .
ruff format --check .
python .github/file_guide_check.py
python -m pytest skills/dev-setup/scripts hooks evals
python .github/holdout_check.py
```
בסביבה נקייה: קודם `pip install pytest ruff==0.17.2`.
