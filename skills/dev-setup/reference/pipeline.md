# צינור העבודה ב-GitHub: הליבה

המסמך הזה הוא המקור היחיד למנגנון שעליו עובדים הסקילים הגנריים `dev-issue`, `dev-next`,
`dev-plan`, `dev-code`, `dev-ship` ו-`dev-setup`, בכל repo. הם מפנים אליו במקום לשכפל
אותו. שינוי בשמות התוויות או בסדר השלבים מתעדכן כאן קודם.

המנגנון נולד ב-WayOut (`dolev2/WayOut`), הועתק ל-CRM (`dolev2/charging-crm`) ב-2026-10-23,
והוכלל לכל הפרויקטים ב-2026-10-25. כל "מוקש" שמתועד כאן קרה באחד מהם.

**אין רוטינות ענן.** כל שלב (Plan, Code, Ship) רץ רק כשדולב מבקש אותו בסשן מקומי.

## מה משתנה מ-repo ל-repo, ואיפה זה נמצא

שום דבר לא מוגדר ידנית בסקילים. כל ריצה מתחילה ב:

```bash
python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
```

| מה | מאיפה | דוגמה |
|---|---|---|
| ה-repo | `gh repo view` | `dolev2/charging-crm` |
| ה-branch הראשי | `defaultBranchRef` | `master` (בהמשך: `<default>`) |
| תווית האדם | תווית `owner:*` שאינה `owner:claude` | `owner:dolev` (בהמשך: `owner:<human>`) |
| שם הסמן המוסתר | המשתנה `SYNC_MARKER` | `crm-sync`, `wayout-sync` |
| מספר הלוח | משתנה ה-repo `PROJECT_NUMBER` | `5` |
| הספרינט הנוכחי | ה-milestone הפתוח הנמוך ביותר שיש בו issues פתוחים | `W1 - CRM + Gmail` |
| פקודות הבדיקה | `CLAUDE.md` של ה-repo, סעיף הבדיקות; האזור של כל חבילה נגזר מהנתיב שבפקודה (ראו "בדיקות" למטה) | כולל חבילות מותנות כמו `-m live`, או "אין חבילה, הבדיקה היא preview" |
| הרמת האפליקציה לסקירה | `CLAUDE.md` של ה-repo, סעיף "הרמה לסקירה" (ראו "הרמה לסקירה" למטה) | פקודה, פורטים וכתובת, או "אין אפליקציה" |
| מקורות האמת לדרישות | `CLAUDE.md` של ה-repo | עמוד התוכנית, `docs/` |
| כותרות גוף ה-issue | הטפסים `task.yml` ו-`bug.yml`, מהמקום ש-`issue_forms` מראה (בדרך כלל `dolev2/.github`), ורמת הכותרות של ה-issues הקיימים | `מה רוצים`; issue ישן יכול להיות באנגלית (`Goal`) |
| שורת התלות ותתי-כותרות ה-Plan | `CLAUDE.md` של ה-repo; בלי הנחיה שם, הנוסח העברי במסמך הזה | `תלוי ב:` / `Depends on:` |
| תוויות `area:*` | התוויות שקיימות ב-repo | |
| נהלי הקוד, git והסביבה | `~/.claude/rules/` (כללי, Python, React, git, Windows), לכל ה-repos | גודל קובץ, שכבות, rebase לפני בדיקות |
| הגדרות ה-lint | עותק בכל repo של `dev-setup/templates/ruff.toml` ו-`eslint.config.js`; `pipeline_info.py` מדווח תחת `lint` על חסר או שונה | `missing ruff.toml` |
| כלל הדילוג של Netlify | `netlify.toml` של ה-repo, לפי `dev-setup/templates/netlify.toml`; `pipeline_info.py` מדווח תחת `netlify` כשאין בו `build.ignore` (ראו "Netlify" למטה) | `no build.ignore in netlify.toml` |
| מה כל קובץ ולמה הוא קיים | סעיף "מדריך קבצים" ב-`README.md` של ה-repo. העותק `.github/file_guide_check.py` בודק ב-CI שהוא שלם; `pipeline_info.py` מדווח תחת `lint` כשהעותק חסר או שונה | `dev-setup` יוצר אותו, וכל שינוי שמוסיף קובץ מעדכן אותו |
| סוגי issues נוספים | תוויות שקיימות ב-repo, למשל `decision` | |

**`CLAUDE.md` של repo מכיל רק את מה שספציפי לו.** נהלי הקוד, git והסביבה נטענים בכל סשן מ-`~/.claude/rules/`, ולכן לא חוזרים עליהם שם: ה-repo כותב רק איפה הדברים אצלו (השכבות, מקור ה-tokens, המילון).

**הכותרות והנוסחים העבריים במסמך הזה הם של התבנית הסטנדרטית.** repo שהתבניות שלו באנגלית,
או שה-issues שלו כתובים ב-`##` ולא ב-`###`, נכתב בכותרות וברמה שלו. בכל מקום שכתוב כאן "מה
רוצים", "תלוי ב:", "שאלות פתוחות" או "יומן שינויים בתוכנית", הכוונה לסעיף המקביל ב-repo.

**שפה:** דיווחים לדולב ותגובות ב-issues בעברית. קוד, שמות branches וכותרות milestones באנגלית.

`ready: False` פירושו שהצינור לא הותקן ב-repo הזה. במקרה כזה מפעילים את `dev-setup` ולא
מאלתרים.

**סקילים ספציפיים ל-repo גוברים.** אם ב-`.claude/skills/` של ה-repo יש סקיל שמכסה את אותו שלב
(למשל `<repo>-plan`), משתמשים בו ולא בגרסה הגנרית. `pipeline_info.py` מציג אותם
תחת `repo_skills`.

## אוצר המילים

| תווית | משמעות | מי מזיז הלאה |
|---|---|---|
| `owner:claude` | ממתין ל-Claude | Claude, כשסיים |
| `owner:<human>` | ממתין לדולב | דולב |
| `status:explore` | ממתין לתכנון | Claude (Plan) |
| `status:plan-questions` | יש שאלה פתוחה על התוכנית, של Claude או של דולב | מי ש-`owner` מצביע עליו |
| `status:waiting-approval` | התוכנית מוכנה, ממתינה לאישור | דולב |
| `status:ready-to-execute` | מאושר לביצוע | Claude (Execute) |
| `status:needs-repair` | חזר לתיקון אחרי בדיקה | Claude (Execute) |
| `status:in-review` | Claude סיים, PR פתוח | דולב |
| `status:done` | אושר, מוכן ל-merge | Claude (Merge, רק בבקשה מפורשת) |
| `status:backlog` | רעיון, לא בצינור | דולב |
| `area:*` | אזור, לפי מה שקיים ב-repo | Claude ממלא אם חסר |
| `bug` / `task` | סוג | — |
| `process` | משימה על ניהול העבודה ולא על הפרויקט: הצינור, עמידה בנהלים של `~/.claude/rules/`, יישור קו עם claude-config (lint שסטה, מדריך קבצים חסר). עולה ראשונה בדירוג, ותמיד בספרינט הנוכחי | Claude, בפתיחה (`dev-issue`) או בתכנון (`dev-plan`). לא בריפו claude-config, שכל משימה בו כזו |
| `costs-money` | המשימה דורשת הוצאה כספית (שירות ענן, API בתשלום, מנוי), ומושהית עד שדולב מאשר את ההוצאה. יוצאת מהדירוג של כל הסריקות, ו-`dev-next` לא מציע אותה. משימה שדולב ביקש בשמה עובדת כרגיל | Claude מוסיף בתכנון (`dev-plan`) או לבקשת דולב. רק דולב מסיר |
| `has-open-questions` | נכתבת רק ע"י שער השאלות | — |

`status:*` ו-`owner:*` הן קבוצות בלעדיות. תמיד להסיר את הקודמת באותה פקודה שמוסיפה את החדשה:

```bash
gh issue edit <N> --add-label "status:waiting-approval" --add-label "owner:<human>" \
                  --remove-label "status:explore"  --remove-label "owner:claude"
```

## מה למצוא בתחילת ריצה

```bash
gh issue list --state open --label "owner:claude" --json number,title,labels,updatedAt
```

סדר הטיפול: `status:needs-repair` לפני `status:ready-to-execute` לפני `status:plan-questions`
לפני `status:explore`. קודם לתקן משהו שדולב כבר בדק, אחר כך לסיים משהו שהתחלנו, ורק בסוף
להתחיל חדש. בתוך כל רמה, לפי הדירוג בסעיף "סדר בתוך הספרינט".

**מ-`waiting-approval` חזרה לתכנון זה מסלול לגיטימי.** אם יש לדולב הסתייגות, הוא כותב אותה
בתגובה ומחזיר ל-`status:plan-questions` + `owner:claude`. התווית משמשת בשני הכיוונים, ומה
שמבדיל ביניהם הוא `owner`. תווית נפרדת (`status:plan-rejected`) נשקלה ונדחתה.

**`status:plan-questions` + `owner:claude` שייך לשלב ה-Plan.** זה המצב שאליו ה-issue נוחת
ברגע שדולב עונה. ב-24.09.2026 זה היה חור אמיתי: Plan חיפש רק `explore` ו-Code רק
`ready-to-execute`/`needs-repair`, וה-issue נתקע בשקט. שתי השאילתות של Plan הן התיקון; אל
תאחד אותן.

## ספרינטים: milestones, לא שדה Iteration

**הספרינט הוא milestone של GitHub.** milestone הוא ברמת ה-repo, ו-`gh issue list --milestone`
פשוט עובד. ללוח יש שדה `Milestone` מובנה שמשקף אותו. הכותרות באנגלית בכוונה, כי הן עוברות
כארגומנט בשורת פקודה. ייתכן שלכל milestone יש issue עוטף, והמשימות הן sub-issues שלו; ה-CLAUDE.md
של ה-repo אומר אם כן.

**הספרינט הנוכחי = ה-milestone הפתוח בעל המספר הנמוך ביותר שיש בו issues פתוחים.** אין תאריכי
יעד (החלטה מודעת, 2026-09-24). כשספרינט נגמר, הבא הופך לנוכחי בלי שאף אחד מעדכן.

**הכלל שחייב להישמר:** סריקה (בלי מספר issue) לא מושכת משימה מחוץ ל-milestone הנוכחי, **גם
כשהתור ריק**. תור ריק פירושו שהספרינט נקי: לדווח ולעצור.

**issue שדולב נקב בשמו** ("תממש את #50") מטופל גם כשהוא מחוץ לספרינט או בלי milestone (החלטה
ב-WayOut #119, 2026-10-25). מציינים בדיווח שהוא מחוץ לספרינט, ולא משייכים לו milestone. כל שאר
השערים (`owner:claude`, Blocked by, WIP) חלים עליו כרגיל.

משימה בלי milestone היא backlog מכוון. אין לגעת בה.

**issue פעיל בלי milestone מדווח, ולא מתוקן לבד** (claude-config #55). פעיל: פתוח, עם תווית
`status:`, שהיא לא `backlog` ולא `done`. אף סריקה לא מגיעה אליו, ולכן הוא נעלם מהעין (WayOut
#42 ו-#117 הגיעו ככה מ-Trello). `rank_issues.py` מציג אותם בשורה האחרונה (`Active, no sprint`)
ו-`dev-next` מדווח עליהם. הסנכרון המרכזי סופר אותם בלוג. זו התראה ולא שגיאה, כי issue שדולב
נקב בשמו מותר לתכנן גם מחוץ לספרינט. השיוך לספרינט נשאר החלטה של דולב.

**באג ומשימת `process` נפתחים תמיד בספרינט הנוכחי**, בלי לשאול (claude-config #38). זה החריג
היחיד לכלל ש-milestone הוא החלטה של דולב, והוא חל רק בפתיחה (`dev-issue`).

## הכללים שלא משתנים

- לא לנחש על issue לא ברור. לשאול בתגובה ולהעביר ל-`owner:<human>`.
- לא לבצע merge בלי בקשה מפורשת של דולב על ה-issue הספציפי, גם כשהתווית `status:done`.
- לא לגעת ב-issue שאין עליו `owner:claude`.
- לא להמציא נתונים עסקיים. מה שחסר הוא שאלה פתוחה, לא טקסט.
