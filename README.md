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
| `settings.json` | ההגדרות של Claude Code לכל הפרויקטים: כללי הרשאות (חלון אישור לפני `gh pr merge`, ואישור מראש לכלי קריאה, לכלי הסשן ולשלושת הכלים שהבן של המתזמר צריך, #155, #150), hooks ומשתני סביבה | גיבוי והיסטוריה. Claude Code עצמו כותב לקובץ (למשל `/config`), ושינוי כזה נכנס לריפו ב-PR |
| `hooks/` | הסקריפטים של ה-hooks והבדיקות שלהם. `block_force_push.py` חוסם `git push --force`, `--mirror` ו-`send-pack --force` (#61, #163). `block_merge_subject.py` חוסם מיזוג עם כותרת commit שנכתבה ביד (`gh pr merge --subject` או `-t`, ו-`commit_title` ב-`gh api` ובכלי ה-MCP), כדי שהכותרת תילקח מכותרת ה-PR (#87, #135). `ask_before_merge.py` מקפיץ חלון אישור לפני כל מיזוג של PR: `gh pr merge` (גם עם `-R`), `gh api`, GraphQL, `gh alias` וכלי ה-MCP של GitHub. כלל ה-ask תופס רק פקודה שמתחילה ב-`gh pr merge` (#135, #163). `guard_main_folder.py` חוסם בתיקייה הראשית של `~/.claude` עריכה של קובץ מהריפו או של קובץ חי שה-`.gitignore` מסתיר (`.git/`, `__pycache__/`, `skills/synced/`), ופקודות git שמחליפות branch או מוחקות עבודה שלא נשמרה (`checkout`, `switch`, `reset --hard`, `stash` ודומיהן) (#62, #163). `guard_parallel_parts.py` חוסם סוכן בעבודה במקביל (`dev-code`, שלב 5) מלערוך קובץ מחוץ לקידומות של החלק שלו, לפי `parallel-parts.json` שבתיקיית ה-git המשותפת (#82). `ps1_bom.py` מוסיף BOM לקובץ `.ps1` אחרי Write או Edit (#63). `ruff_on_edit.py` מריץ `ruff format` על קובץ Python אחרי Write או Edit, ומחזיר ל-Claude את שגיאות ה-lint שנשארו, בלי `--fix` (#64). `cloud_refresh.py` מעדכן את `~/.claude` ל-`main` בתחילת כל סשן ענן, כי סביבת הענן ממחזרת תמונה של המחשב עד שבעה ימים (#132). עם `--report` הוא מדפיס אם הרענון קרה ולמה לא, בשביל המתזמר באמצע ספרינט (#192). `compact_after_merge.py` דואג שאחרי מיזוג של PR ההודעה האחרונה של התור תיגמר בבלוק `/compact` מלא: אחרי המיזוג הוא מזכיר ומסמן את הסשן, ובסוף התור עוצר פעם אחת כשהבלוק חסר (#199). `guard_create_session.py` מקפיץ חלון אישור לפני `create_session` כשהסשן-הבן מקבל כלי מחוץ לרשימה שהבן של המתזמר צריך (כמו `Bash(...)` או `*`), או כשהוא נפתח בסביבה אחרת (#175). `test_settings_permissions.py` שומר על רשימת `allow` ב-`settings.json`: רק כלים שקוראים או שנוגעים בסשן עצמו, ושלושת הכלים שהבן של המתזמר צריך (`CHILD_TOOLS`, #150), בשמות מלאים, ולא כלי שה-hook של המיזוג שומר עליו (#155). `shell_commands.py` הוא הקוד המשותף להם: קריאת הקלט, הקובץ שעריכה כותבת, ה-subcommand של `gh` ושל `git`, וזיהוי של פקודה שממזגת PR. `shell_split.py` מפרק שורת shell לפקודות שהיא מריצה: סוגריים, `if`, `$(…)`, `bash -c`, `eval` ועוטפים כמו `env` ו-`timeout` (#163). `shell_strip.py` מסיר ממנה את מה שלא רץ, גופי heredoc והערות `#`, במעבר אחד שמכיר מרכאות, `$(…)`, חשבון `$((…))` ו-`"${…}"` (#172, #194) | אכיפה של כללים כתובים. אם Python חסר, ה-hook לא חוסם (נכשל בלי לעצור), בכוונה |
| `.claude/CLAUDE.md` | ההנחיות לעבודה על הריפו הזה | נטען רק בסשן שעובד בתוך הריפו |
| `.github/workflows/tests.yml` | CI: lint והבדיקות על כל PR ועל כל push ל-`main` | אותן פקודות כמו בסעיף "בדיקות" ב-`.claude/CLAUDE.md` |
| `.github/workflows/open-questions-gate.yml`, `sync-project.yml` | הצינור של הריפו הזה עצמו | המשימות של הריפו מנוהלות באותו צינור כמו כל פרויקט |
| `.github/file_guide_check.py` | בודק שמדריך הקבצים הזה מונה כל קובץ, ורק קבצים שקיימים: עותק של `skills/dev-setup/templates/file_guide_check.py`, עם החריגים של הריפו מתחת לשורת `--- local ---` | רץ ב-CI. הריפו שמגדיר את הבדיקה לכל הריפואים עומד בה בעצמו (#89) |
| `docs/decisions/*.md` | דף לכל החלטה שחוצה משימות: מצב, רקע, החלטה, חלופות שנדחו ומחיר. דף לא משנים: החלטה חדשה מחליפה אותו (#187) | הכלל ב-`rules/` אומר מה, והדף אומר למה ומה נדחה. סשן חדש מגיע אליו מההפניה בכלל, ולא מציע שוב את מה שנדחה |
| `docs/retros/151-global-config.md` | רטרו חד-פעמי של הספרינט "Global config" עם המתזמר: איפה חיכו, עבודה כפולה, והצעות מדורגות לייעול (#151) | הבסיס להחלטה של דולב אילו הצעות נפתחות כ-issues. דוח ולא נוהל: שום סקיל לא קורא אותו |

### `rules/`: כללים לכל הפרויקטים
| קובץ | מה הוא | מתי נטען |
|---|---|---|
| `code-general.md` | נהלי קוד כלליים: מודולריות, שמות, תיעוד | תמיד |
| `code-tests.md` | נהלי בדיקות: סוגי הבדיקות, מה חובה לבדוק לפי סוג השינוי, נתוני בדיקה ו-mock | תמיד |
| `code-python.md` | נהלי Python: שלוש שכבות, סגנון, pytest | רק כשעובדים על קבצי Python (`paths`) |
| `code-react.md` | נהלי React, ובדיקות ב-Testing Library | רק כשעובדים על קבצי React (`paths`) |
| `git.md` | נהלי git: מאיפה חותכים branch, rebase ואז בדיקות, התנגשות, worktree | תמיד |
| `erd.md` | נוהל ה-ERD: איפה התרשים גר, בלוק הנתונים, הבדיקה מול המודלים, ומה מוצג בו (#118) | תמיד, כי הוא חל כבר בתכנון של שינוי סכמה |
| `env-windows.md` | נהלי הסביבה במחשב של דולב: Windows, קידוד עברית, כלים זמינים, ומה חייב לעבוד גם מחוץ ל-Windows | תמיד |
| `env-cloud.md` | נהלי הסביבה בסשן ענן: Linux, הכלים שמותקנים שם (כולל Playwright), רשת ו-GitHub דרך REST, ומה נשאר למחשב (#136) | תמיד, והוא חל רק כש-`CLAUDE_CODE_REMOTE=true` |

### `skills/`: הסקילים של צינור העבודה
| סקיל | מה עושה |
|---|---|
| `dev-issue` | פותח issues ומפרק משימות |
| `dev-next` | בוחר את המשימה הבאה בספרינט |
| `dev-plan` | שלב התכנון |
| `dev-code` | שלב הביצוע, עד PR ב-`status:in-review`. המיזוג ב-`dev-ship` |
| `dev-ship` | שחרור branch מההתחלה ועד הסוף |
| `dev-orchestrate` | מריץ את כל הספרינט מסשן ענן אחד: סשן-בן לכל משימה שלא חסומה, ושאלות ומיזוגים רק דרכו (#150) |
| `dev-setup` | מתקין את הצינור בריפו חדש, ומחזיק את החלקים המשותפים (הטבלה הבאה) |

### `skills/dev-setup/`: הבית המשותף של הצינור
| קובץ | מה הוא | למה הוא קיים |
|---|---|---|
| `reference/pipeline.md` | הליבה של המנגנון: מה משתנה בין ריפואים, אוצר המילים, הספרינטים, הכללים שלא משתנים, ורשימת שאר הקבצים כאן | כל סקיל `dev-*` קורא אותו, ובנוסף רק את הקבצים שה-"Read first" שלו מונה |
| `reference/issue-body.md` | קריאת כל ההקשר של issue, פורמט ה-Plan, עריכת הגוף, סעיף השאלות הפתוחות | `dev-issue`, `dev-plan`, `dev-code`, `dev-ship`, `dev-next` (בסקירת הסדר) |
| `reference/dependencies.md` | קישורי Blocked by, פיצול ואיחוד, הדירוג בספרינט, הקודים של `audit_sprint.py` | `dev-issue`, `dev-next`, `dev-plan` |
| `reference/git-flow.md` | issue אחד בריצה ושער ה-WIP, עותק העבודה בכל שלב, branch ו-PR, rebase ו-CI לפני merge | `dev-plan`, `dev-code`, `dev-ship` |
| `reference/tests.md` | אילו בדיקות רצות, ומתי: ממוקד בפיתוח, מלא פעם אחת אחרי ה-rebase | `dev-code`, `dev-ship`, `dev-setup` |
| `reference/review-app.md` | הרמת האפליקציה של ה-PR לסקירה, קובץ הרישום, ועצירה | `dev-code`, `dev-ship`, `dev-setup` |
| `reference/ux.md` | רשימת הבדיקה של חוויית משתמש: הסעיף בתוכנית, והמעבר על הפיצ'ר בדפדפן לפני המסירה | `dev-plan`, `dev-code` |
| `reference/after-merge.md` | ההצעה לסשן של המשימה הבאה אחרי מיזוג | `dev-ship` |
| `reference/setup.md` | מה ש-`dev-setup` מתקין ולמה: הסנכרון עם הלוח, הטפסים, השער, Netlify, lint | `dev-setup` בלבד, כדי ששאר הסקילים לא יקראו אותו |
| `reference/board.md` | לוח ה-Project בהתקנה: יצירה וקישור, `EXPECTED_BOARDS`, שדה Status, פקודת ה-token ל-PowerShell ול-bash, והתצוגות | `dev-setup` בלבד. יצא מהסקיל כדי שיישאר מתחת ל-300 שורות (#168) |
| `reference/repo-files.md` | הקבצים שההתקנה מוסיפה לריפו: הגדרות lint, כלל הדילוג של Netlify, מדריך הקבצים והבדיקה שלו | `dev-setup` בלבד. יצא מהסקיל כדי שיישאר מתחת ל-300 שורות (#168) |
| `reference/parallel.md` | עבודה במקביל: קובץ החלקים, סוכן לכל חלק, הבדיקה, החיבור והניקוי | `dev-code` בלבד, כשבתוכנית יש "עבודה במקביל". יצא מהסקיל כדי שיישאר מתחת ל-300 שורות (#168) |
| `reference/chat-decisions.md` | החלטות של דולב בחלון השאלות בצ'אט: תשובה לשאלות, אישור תוכנית, מיזוג או תיקון. מה נחשב החלטה, ובאיזה סדר | `dev-plan`, `dev-code` ו-`dev-next` קוראים אותו, ו-`dev-ship` מפנה אליו. יצא מ-`pipeline.md` כדי שהליבה תישאר קצרה (#126) |
| `reference/orchestrate.md` | המתזמר והסשנים-הבנים: איך נפתח בן, החוזה שעובר אליו ב-`append_system_prompt`, מה בודקים אחרי דיווח, באג, ומיזוג | `dev-orchestrate`. החוזה כתוב פעם אחת, כדי שכל בן יקבל אותו מילה במילה (#150) |
| `reference/cloud.md` | עבודה מסשן ענן ומהטלפון: Remote Control, הגדרת סביבת הענן וסקריפט ההתקנה שלה, ומה שונה בענן | בסשן ענן `~/.claude` שייך לשירות, ובלי ההתקנה לא נטען שם כלום מהריפו הזה (#132). `test_cloud_setup.py` מריץ את הסקריפט כמו שהוא |
| `reference/diagram.md` | תרשים ה-Mermaid של הצינור, וכלל העריכה שלו | לבני אדם; אף סקיל לא קורא אותו בזמן ריצה |
| `reference/issue-lifecycle.html` | העמוד "חייו של issue": מפת התוויות, ציר git, טבלת שלבים וכללי git, לבני אדם. מפורסם כ-Artifact | הסקילים קוראים את `reference/*.md`, חוץ מ-`diagram.md`. העמוד הוא התצוגה, ומתעדכן באותו PR (`.claude/CLAUDE.md`) |
| `reference/issue-lifecycle-en.html` | אותו עמוד באנגלית ("Life of an Issue"), מפורסם כ-Artifact נפרד | מי שלא קורא עברית. כל שינוי באחת הגרסאות משתקף בשנייה באותו PR (`.claude/CLAUDE.md`) |
| `scripts/pipeline_info.py` | קורא מהריפו כל מה שמשתנה בין ריפואים | כל סקיל מתחיל בו, כדי ששום דבר לא יוגדר ידנית |
| `scripts/sprint_rule.py` | הכלל היחיד לספרינט הנוכחי: ה-milestone הפתוח הנמוך ביותר שיש בו issue פתוח, בלי לספור PRים | `rank_issues.py`, `pipeline_info.py` והתצוגה "ספרינט נוכחי" בחרו קודם ספרינטים שונים (#164) |
| `scripts/rank_issues.py` | מדרג את ה-issues בספרינט לפי כמה עבודה מחכה להם | הסדר של `dev-next`, `dev-plan` ו-`dev-code` |
| `scripts/audit_sprint.py` | בודק את קישורי ה-Blocked by של כל הספרינט יחד: קישור חסר, חוסם מחוץ לספרינט, מעגל, חפיפת קבצים (#54) | הדירוג טוב רק כמו הקישורים; `dev-next` מריץ אותו בכל ריצה |
| `scripts/sprint_state.py` | מחזיר את מצב הספרינט כ-JSON אחד: מה מוכן לסשן-בן, מה מחכה לחפיפת קבצים (מהתוכנית ומה שה-branch כבר שינה, #203), לחוסם או לדולב, תור המיזוג עם ה-CI ועם הבנים הפעילים שנוגעים באותם קבצים, הממצאים של `audit_sprint.py`, עוטפות שמחכות ל-sub-issue פתוח, ושני מזהי הצינור מ-`pipeline_shas.py` | המתזמר של הספרינט לא זוכר כלום בין בדיקות, ובונה את התמונה מחדש מ-GitHub בכל בדיקה (#150, #174) |
| `scripts/pipeline_shas.py` | קורא את שני מזהי הצינור בשביל `sprint_state.py`: הקומיט האחרון ב-main של claude-config שנגע במה שנטען מהדיסק בכל שימוש, ובמה שסשן טוען פעם אחת בתחילתו. נקרא מ-git, מ-clone בלי blobs ב-cache, ולא מה-API | המתזמר מזהה שהצינור השתנה באמצע ספרינט גם מסשן של ריפו אחר (#192, #211), וזה יצא מ-`sprint_state.py` כדי שיישאר מתחת לסף הגודל (#214) |
| `scripts/sprint_github.py` | קורא מ-GitHub בשביל `sprint_state.py`: מצב המיזוג וה-CI של PR, הקבצים ש-PR משנה, והקבצים ש-branch כבר שינה מול ה-branch הראשי | הקריאות לרשת מחוץ ללוגיקה, כדי שהבדיקות של `sprint_state.py` ירוצו בלי רשת (#203) |
| `scripts/watch_children.py` | מחכה עד שה-status של issue של בן פעיל זז או שנוספת בו תגובה שלא המתזמר כתב (הסמן `<!-- orchestrator -->`, #203), מדפיס מה השתנה ויוצא. המתזמר מריץ אותו ברקע | הבן לא שולח הודעות, כי השירות מקפיץ חלון על כל `send_message`. היציאה של הסקריפט היא מה שמעיר את המתזמר (#184) |
| `scripts/gh_rest.py` | קורא את ה-issues הפתוחים מ-GitHub דרך REST בלבד, באותה צורה שבה GraphQL החזיר אותם, ומנסה שוב כשהרשת או GitHub נכשלים לרגע | GraphQL חסום בסשן ענן; משותף ל-`rank_issues.py`, `audit_sprint.py`, `sprint_state.py` ו-`pipeline_info.py` (#138, #174) |
| `scripts/issue_body.py` | קורא את הסעיפים של גוף issue: המטרה, ההקשר, שורת התלות, וה-branch והקבצים מה-Plan | משותף ל-`audit_sprint.py` ול-`sprint_state.py` |
| `scripts/board_views.py` | יוצר את שתי התצוגות של הלוח, "ספרינט נוכחי" ו"הכל" | התקנה של לוח בלי עבודה ידנית |
| `scripts/port_check.py` | בודק אם פורט תפוס, ובוחר פורט פנוי, גם ב-`127.0.0.1` וגם ב-`::1` | הרמה לסקירה; Vite מאזין רק ב-IPv6, ובדיקה של IPv4 לבד פספסה אותו (#52) |
| `scripts/lint_check.py` | מדווח על הגדרות lint שחסרות בריפו, או ששונות מהתבנית, ועל עותק חסר או שסטה של בדיקת מדריך הקבצים | כדי שהעותקים בכל ריפו לא יסטו בשקט |
| `scripts/test_*.py` | הבדיקות של הסקריפטים, של שני ה-actions ושל התבניות | רצות ב-CI |
| `actions/open-questions-gate/` | שער השאלות הפתוחות, action שכל ריפו קורא לו: `action.yml` מריץ את `check_open_questions.py` | עותק אחד לכל הריפואים |
| `actions/project-sync/` | הסנכרון מהתוויות ללוח, בכיוון אחד, action שכל ריפו עם לוח קורא לו. `action.yml` מריץ את `sync_project.py` | עותק אחד לכל הריפואים |
| `actions/project-sync/sync_project.py` | נקודת הכניסה של הסנכרון: ההגדרות מהסביבה, הלולאה על ה-issues, ומה מודפס | `action.yml` ו-`sweep_all.py` מריצים אותו בשם הזה |
| `actions/project-sync/sync_rules.py` | הכללים: איזה issue מסונכרן, מה נכתב ללוח, החריג של issue שנפתח מהלוח, ושמות האופציות בלוח (`STATUS_OPTIONS`) | בלי קריאות ל-GitHub, כדי שאפשר לבדוק אותם לבד (#57) |
| `actions/project-sync/board.py` | קריאה וכתיבה של הלוח, מצד ה-issue | `projectV2.items` מחזיר רשימה ריקה (המוקש ב-`reference/setup.md`) |
| `actions/project-sync/sprint_rule.py` | עותק של `scripts/sprint_rule.py` | הסנכרון מורד כתיקייה שטוחה; `test_sprint_rule.py` שומר שהשניים זהים (#164) |
| `actions/project-sync/sprint_view.py` | מזיז את הסינון של התצוגה "ספרינט נוכחי" לספרינט הנוכחי | ל-GitHub אין `milestone:@current` (#17) |
| `actions/project-sync/gh_api.py` | הקריאות ל-`gh` ול-GraphQL, עם ניסיון חוזר על שגיאה זמנית (502/503/504) | מקום אחד שהבדיקות מחליפות; שגיאה זמנית הפילה ריצות (#105) |
| `scripts/conftest.py` | מוסיף את `actions/project-sync/` לנתיב של הבדיקות | כדי שהבדיקות ייבאו את המודולים בשמם, כמו שהסקריפט עושה |
| `actions/project-sync/sweep_all.py` | הסקר המתוזמן של כל הלוחות בבת אחת: מחזיר כרטיסים שנגררו ביד, ומדפיס רק מספרים. נכשל כשמספר הלוחות שונה מ-`EXPECTED_BOARDS` (#49) | רץ מהריפו הציבורי `dolev2/.github`, כי שם דקות ה-Actions בחינם (#46) |
| `templates/.github/workflows/` | שני ה-workflows הקצרים שקוראים ל-actions, `open-questions-gate.yml` ו-`sync-project.yml`, ושלד של `tests.yml` עם צעדי lint ובדיקת מדריך הקבצים | מועתקים לכל ריפו בהתקנה |
| `templates/ruff.toml` | הגדרות ruff ל-Python, לפי נהלי הקוד | כל ריפו עם Python מקבל עותק |
| `templates/eslint.config.js` | הגדרות eslint ל-React ב-JavaScript, לפי נהלי הקוד | כל ריפו עם React מקבל עותק |
| `templates/README.md` | שלד של מדריך קבצים | `dev-setup` יוצר ממנו מדריך בריפו שאין לו |
| `templates/file_guide_check.py` | הבדיקה שמדריך הקבצים שלם: קובץ שלא מופיע בו, או שורה על קובץ שלא קיים. קוראת רק את טבלאות המדריך | כל ריפו מקבל עותק ב-`.github/`, עם חריגים משלו, ומריץ אותו ב-CI (#89) |
| `templates/erd.html` | עמוד ERD כללי: הקוד שמצייר קורא הכל מבלוק `erd-data`, עם דוגמה של שתי טבלאות | ריפו עם מסד מעתיק אותו ל-`docs/erd.html` בשינוי הסכמה הראשון (`rules/erd.md`) |
| `templates/test_erd.py` | הבדיקה שמשווה את בלוק ה-ERD למודלים של SQLAlchemy, בלי מסד | מועתק לצד העמוד, כדי שהתרשים לא יתיישן בשקט |
| `templates/netlify.toml` | כלל הדילוג של Netlify, בשתי צורות: אתר בתיקייה משלו ואתר בשורש | כל deploy עולה קרדיטים, ובלי הכלל כל מיזוג של הצינור הוא deploy (#50) |
| `templates/decision.md` | שלד של דף החלטה: שורת מצב וארבעת החלקים | ריפו מעתיק אותו ל-`docs/decisions/` בהחלטה הרוחבית הראשונה שלו (`rules/code-general.md`). `scripts/test_decisions.py` בודק אותו ואת הדפים |
| `templates/ruleset-main.json` | ה-ruleset `protect-main` של ה-branch הראשי: חובת PR בלי אישור סוקר, בלי force push, בלי מחיקה, squash בלבד. זהה למה שמוגדר על claude-config | `dev-setup` שולח אותו ל-API בריפו ציבורי, כדי שאף סשן לא ידחוף ישר ל-branch הראשי (#162) |

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
