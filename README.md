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
| `settings.json` | ההגדרות של Claude Code לכל הפרויקטים: כללי הרשאות (חלון אישור לפני `gh pr merge`), hooks ומשתני סביבה | גיבוי והיסטוריה. Claude Code עצמו כותב לקובץ (למשל `/config`), ושינוי כזה נכנס לריפו ב-PR |
| `hooks/` | הסקריפטים של ה-hooks והבדיקות שלהם. `block_force_push.py` חוסם `git push --force` (#61). `block_merge_subject.py` חוסם `gh pr merge` עם `--subject` או `-t`, כדי שכותרת ה-commit תילקח מכותרת ה-PR (#87). `guard_main_folder.py` חוסם עריכה של קובץ מהריפו, ו-`git checkout`/`git switch`, בתיקייה הראשית של `~/.claude` (#62). `guard_parallel_parts.py` חוסם סוכן בעבודה במקביל (`dev-code`, שלב 5) מלערוך קובץ מחוץ לקידומות של החלק שלו, לפי `parallel-parts.json` שבתיקיית ה-git המשותפת (#82). `ps1_bom.py` מוסיף BOM לקובץ `.ps1` אחרי Write או Edit (#63). `ruff_on_edit.py` מריץ `ruff format` על קובץ Python אחרי Write או Edit, ומחזיר ל-Claude את שגיאות ה-lint שנשארו, בלי `--fix` (#64). `shell_commands.py` הוא הקוד המשותף להם: קריאת הקלט, הקובץ שעריכה כותבת, ופירוק פקודות shell | אכיפה של כללים כתובים. אם Python חסר, ה-hook לא חוסם (נכשל בלי לעצור), בכוונה |
| `.claude/CLAUDE.md` | ההנחיות לעבודה על הריפו הזה | נטען רק בסשן שעובד בתוך הריפו |
| `.github/workflows/tests.yml` | CI: lint והבדיקות על כל PR ועל כל push ל-`main` | אותן פקודות כמו בסעיף "בדיקות" ב-`.claude/CLAUDE.md` |
| `.github/workflows/open-questions-gate.yml`, `sync-project.yml` | הצינור של הריפו הזה עצמו | המשימות של הריפו מנוהלות באותו צינור כמו כל פרויקט |
| `.github/file_guide_check.py` | בודק שמדריך הקבצים הזה מונה כל קובץ, ורק קבצים שקיימים: עותק של `skills/dev-setup/templates/file_guide_check.py`, עם החריגים של הריפו מתחת לשורת `--- local ---` | רץ ב-CI. הריפו שמגדיר את הבדיקה לכל הריפואים עומד בה בעצמו (#89) |

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
| `reference/pipeline.md` | הליבה של המנגנון: מה משתנה בין ריפואים, אוצר המילים, הספרינטים, הכללים שלא משתנים, ורשימת שאר הקבצים כאן | כל סקיל `dev-*` קורא אותו, ובנוסף רק את הקבצים שה-"Read first" שלו מונה |
| `reference/issue-body.md` | קריאת כל ההקשר של issue, פורמט ה-Plan, עריכת הגוף והסמן המוסתר, סעיף השאלות הפתוחות | `dev-issue`, `dev-plan`, `dev-code` |
| `reference/dependencies.md` | קישורי Blocked by, פיצול ואיחוד, הדירוג בספרינט, הקודים של `audit_sprint.py` | `dev-issue`, `dev-next`, `dev-plan` |
| `reference/git-flow.md` | issue אחד בריצה ושער ה-WIP, עותק העבודה בכל שלב, branch ו-PR, rebase ו-CI לפני merge | `dev-plan`, `dev-code`, `dev-ship` |
| `reference/tests.md` | אילו בדיקות רצות, ומתי: ממוקד בפיתוח, מלא פעם אחת אחרי ה-rebase | `dev-code`, `dev-ship` |
| `reference/review-app.md` | הרמת האפליקציה של ה-PR לסקירה, קובץ הרישום, ועצירה | `dev-code`, `dev-ship`, `dev-setup` |
| `reference/after-merge.md` | ההצעה לסשן של המשימה הבאה אחרי מיזוג | `dev-code` Part B, `dev-ship` |
| `reference/setup.md` | מה ש-`dev-setup` מתקין ולמה: הסנכרון עם הלוח, הטפסים, השער, Netlify, lint | `dev-setup` בלבד, כדי ששאר הסקילים לא יקראו אותו |
| `reference/diagram.md` | תרשים ה-Mermaid של הצינור, וכלל העריכה שלו | לבני אדם; אף סקיל לא קורא אותו בזמן ריצה |
| `reference/issue-lifecycle.html` | העמוד "חייו של issue": מפת התוויות, ציר git, טבלת שלבים וכללי git, לבני אדם. מפורסם כ-Artifact | הסקילים קוראים את `reference/*.md`. העמוד הוא התצוגה, ומתעדכן באותו PR (`.claude/CLAUDE.md`) |
| `scripts/pipeline_info.py` | קורא מהריפו כל מה שמשתנה בין ריפואים | כל סקיל מתחיל בו, כדי ששום דבר לא יוגדר ידנית |
| `scripts/rank_issues.py` | מדרג את ה-issues בספרינט לפי כמה עבודה מחכה להם | הסדר של `dev-next`, `dev-plan` ו-`dev-code` |
| `scripts/audit_sprint.py` | בודק את קישורי ה-Blocked by של כל הספרינט יחד: קישור חסר, חוסם מחוץ לספרינט, מעגל, חפיפת קבצים (#54) | הדירוג טוב רק כמו הקישורים; `dev-next` מריץ אותו בכל ריצה |
| `scripts/issue_body.py` | קורא את הסעיפים של גוף issue: המטרה, ההקשר, שורת התלות והקבצים מה-Plan | משותף ל-`audit_sprint.py` |
| `scripts/board_views.py` | יוצר את שתי התצוגות של הלוח, "ספרינט נוכחי" ו"הכל" | התקנה של לוח בלי עבודה ידנית |
| `scripts/port_check.py` | בודק אם פורט תפוס, ובוחר פורט פנוי, גם ב-`127.0.0.1` וגם ב-`::1` | הרמה לסקירה; Vite מאזין רק ב-IPv6, ובדיקה של IPv4 לבד פספסה אותו (#52) |
| `scripts/lint_check.py` | מדווח על הגדרות lint שחסרות בריפו, או ששונות מהתבנית, ועל עותק חסר או שסטה של בדיקת מדריך הקבצים | כדי שהעותקים בכל ריפו לא יסטו בשקט |
| `scripts/test_*.py` | הבדיקות של הסקריפטים, של שני ה-actions ושל התבניות | רצות ב-CI |
| `actions/open-questions-gate/` | שער השאלות הפתוחות, action שכל ריפו קורא לו: `action.yml` מריץ את `check_open_questions.py` | עותק אחד לכל הריפואים |
| `actions/project-sync/` | הסנכרון בין התוויות ללוח, action שכל ריפו עם לוח קורא לו. `action.yml` מריץ את `sync_project.py` | עותק אחד לכל הריפואים |
| `actions/project-sync/sync_project.py` | נקודת הכניסה של הסנכרון: ההגדרות מהסביבה, הלולאה על ה-issues, ומה מודפס | `action.yml` ו-`sweep_all.py` מריצים אותו בשם הזה |
| `actions/project-sync/sync_rules.py` | הכללים: איזה issue מסונכרן, מי מנצח, ושמות האופציות בלוח (`STATUS_OPTIONS`) | בלי קריאות ל-GitHub, כדי שאפשר לבדוק אותם לבד (#57) |
| `actions/project-sync/board.py` | קריאה וכתיבה של הלוח, מצד ה-issue | `projectV2.items` מחזיר רשימה ריקה (המוקש ב-`reference/setup.md`) |
| `actions/project-sync/marker.py` | הסמן המוסתר בגוף ה-issue: קריאה וכתיבה | המצב האחרון שסונכרן, שלפיו מכריעים |
| `actions/project-sync/sprint_view.py` | מזיז את הסינון של התצוגה "ספרינט נוכחי" לספרינט הנוכחי | ל-GitHub אין `milestone:@current` (#17) |
| `actions/project-sync/gh_api.py` | הקריאות ל-`gh` ול-GraphQL | מקום אחד שהבדיקות מחליפות |
| `scripts/conftest.py` | מוסיף את `actions/project-sync/` לנתיב של הבדיקות | כדי שהבדיקות ייבאו את המודולים בשמם, כמו שהסקריפט עושה |
| `actions/project-sync/sweep_all.py` | הבדיקה המתוזמנת של כל הלוחות בבת אחת, ומדפיס רק מספרים. נכשל כשמספר הלוחות שונה מ-`EXPECTED_BOARDS` (#49) | רץ מהריפו הציבורי `dolev2/.github`, כי שם דקות ה-Actions בחינם (#46) |
| `templates/.github/workflows/` | שני ה-workflows הקצרים שקוראים ל-actions, `open-questions-gate.yml` ו-`sync-project.yml`, ושלד של `tests.yml` עם צעדי lint ובדיקת מדריך הקבצים | מועתקים לכל ריפו בהתקנה |
| `templates/ruff.toml` | הגדרות ruff ל-Python, לפי נהלי הקוד | כל ריפו עם Python מקבל עותק |
| `templates/eslint.config.js` | הגדרות eslint ל-React ב-JavaScript, לפי נהלי הקוד | כל ריפו עם React מקבל עותק |
| `templates/README.md` | שלד של מדריך קבצים | `dev-setup` יוצר ממנו מדריך בריפו שאין לו |
| `templates/file_guide_check.py` | הבדיקה שמדריך הקבצים שלם: קובץ שלא מופיע בו, או שורה על קובץ שלא קיים. קוראת רק את טבלאות המדריך | כל ריפו מקבל עותק ב-`.github/`, עם חריגים משלו, ומריץ אותו ב-CI (#89) |
| `templates/netlify.toml` | כלל הדילוג של Netlify, בשתי צורות: אתר בתיקייה משלו ואתר בשורש | כל deploy עולה קרדיטים, ובלי הכלל כל מיזוג של הצינור הוא deploy (#50) |

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

```bash
python .github/file_guide_check.py
python -m pytest skills/dev-setup/scripts hooks
```
