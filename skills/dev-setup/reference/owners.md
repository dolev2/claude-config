# מפת הבעלים: איפה כתוב כל כלל

המפה היא לסוכנים. נקודת הכניסה לבני אדם היא העמוד "חייו של issue" (`issue-lifecycle.html`), שמפנה מכל כלל לקובץ הבעלים שלו.

לכל כלל בצינור יש קובץ בעלים אחד, ובו הנוסח המלא: הכלל, הנימוק והחריגים.
כל מקום אחר מפנה אליו בשם הקובץ, ולא מעתיק אותו. סקיל משאיר לעצמו רק את הצעד שהוא מבצע ואת הפקודה שהוא מריץ.
למה כך, ומה נדחה: `~/.claude/docs/decisions/152-one-owner-per-rule.md`.

**שינוי בכלל מתחיל בקובץ הבעלים שלו.** מפנה שצריך יותר מהפניה (פקודה חדשה, צעד חדש) משתנה באותו PR.
שינוי בשלבים, בתוויות, בשערים, באוטומציות או בצעדי git מעדכן גם את התרשים ואת שני העמודים "חייו של issue" (`.claude/CLAUDE.md` של claude-config).
כלל חדש שכתוב ביותר ממקום אחד מקבל שורה כאן.

| הכלל | הבעלים | מי מפנה אליו |
|---|---|---|
| פירוק ופיצול נפתחים בלי שאלת אישור, ומה נשאר שאלה (S-1.66) | `specs.md`, "הפירוק ל-issues" | `dev-issue` צעד 1 ו"פירוק אפיון", `dev-ship` צעד 8, `dev-orchestrate` צעד 4, `orchestrate.md` ("באג, קישור או פיצול שבן מצא"), `orchestrate-spec.md` סעיף 7 |
| היקף הספרינט: סריקה לא יוצאת מה-milestone הנוכחי, issue שדולב נקב בשמו מותר, Claude לא משייך milestone (חוץ מבאג ו-`process` בפתיחה, פירוק מהמתזמר, ו-milestone בלי מקור בפירוק או בפיצול שנפתחים בלי שאלה) | `pipeline.md`, "ספרינטים" | `dev-plan`, `dev-code`, `dev-next`, `dev-issue` |
| הצעה בבקלוג ששויכה ל-milestone של הספרינט היא הצעה מאושרת: בן אפיון ראשון בתור, אחד בכל פעם, והפירוק שלה נכנס לספרינט שלה (S-2.14) | `specs.md`, "מתי נכתב אפיון" | `orchestrate-spec.md`, `pipeline.md` ("ספרינטים"), `dev-orchestrate`, `dev-spec` צעד 1, `dev-issue` ("פירוק אפיון"), `dev-plan` צעד 2 |
| שער ה-WIP: שלושה ומעלה ב-`status:in-review`, כולל PR שכבר נסקר; תיקון פטור; בן של המתזמר מדלג | `git-flow.md`, "כמה issues בריצה אחת" | `dev-code` שלב 1 (הפקודה), `orchestrate.md` (המתזמר בודק לפני בן קוד) |
| החלטה באה רק מדולב עצמו | `chat-decisions.md`, כלל 3 | `pipeline.md`, `dev-plan`, `dev-code`, `dev-ship` |
| המבחן של "דולב בצ'אט": `AskUserQuestion` בין הכלים של הסשן, בן של מתזמר לא עובר, ומה קורה כשלא עובר (S-1.70) | `chat-decisions.md`, "המבחן של 'דולב בצ'אט'" | `chat-decisions.md` כללים 5 ו-7, `dev-code` שלב 11, `dev-spec` צעדים 5 ו-9, `dev-plan` צעדים 7–8, `dev-ship` ("Relationship to dev-code" וצעד 8), `dev-next` צעד 4, `dev-issue` ("פירוק אפיון"), `follow-ups.md`, `specs.md`, `pipeline.md` |
| עובדות הסביבה בענן: GraphQL חסום, push שמוחק branch חסום, הרשת דרך proxy | `~/.claude/rules/env-cloud.md` | `cloud.md`, `git-flow.md` |
| תרגום פקודות `gh` בענן | `cloud.md`, "פקודות GitHub בסשן ענן" | כל סקיל `dev-*` (שלב 0) |
| צעדי git בענן: ה-branch של המשימה, בלי worktree, החלפת branch בעץ נקי, הניקוי אחרי מיזוג, שם הסשן | `git-flow.md`, "בסשן ענן" | `~/.claude/rules/git.md` (החריג), `cloud.md`, `dev-ship` צעד 7 |
| פקודות הבדיקה של claude-config | `.claude/CLAUDE.md`, "בדיקות" | `README.md` מחזיק עותק מלא בכוונה. בדיקה משווה את שניהם ל-`tests.yml` (`skills/dev-setup/scripts/test_doc_drift.py`) |
| בדיקה ידנית בדפדפן וצילומי מסך: Edge, Playwright, הרוחבים, הצילומים למסירה | `ux.md` | `~/.claude/rules/code-tests.md`, `tests.md`, `~/.claude/rules/env-windows.md` (רק עובדות Edge), `~/.claude/rules/env-cloud.md`, `dev-code` שלב 10 |
| פרסום מחדש של עמוד Artifact אחרי מיזוג: קריאה, השוואה, `publish` בלי `icon` ובלי `force`, השלד | `after-merge.md`, "פרסום מחדש של עמוד Artifact" | `.claude/CLAUDE.md` של claude-config (העמודים והקישורים), `~/.claude/rules/erd.md`, `dev-ship` |
| אות המיזוג: בקשה מוקלדת של דולב, או אישור בחלון ההרשאה אחרי מסירה (S-3.13) או מהמתזמר (S-2.18), על ה-issue הספציפי | `pipeline.md`, "הכללים שלא משתנים" | `chat-decisions.md` כלל 5, `dev-code`, `dev-ship`, `dev-spec`, `dev-orchestrate` צעד 6, `orchestrate.md` ("מיזוג"), `rules/git.md` |
| מתי באג חוזר לתכנון מלא: מחיקה, שינוי חוזה או תלות חדשה | `specs.md`, "באג" | `dev-code` צעד 3, `issue-body.md` |
| issue אחד בכל ריצת קוד, והחריג של כמה משימות שתוכננו באותה ריצה | `git-flow.md`, "כמה issues בריצה אחת" | `dev-code`, `dev-plan` שלב 8, `after-merge.md` |
| התוכנית היא לא שער: תוכנית בלי שאלה מתחילה קידוד באותו סשן, שאלה פתוחה היא העצירה היחידה, ו-`status:waiting-approval` הישנה נקראת כמוכנה לביצוע (S-1.64) | `pipeline.md`, הפסקה "התוכנית היא לא שער" ואוצר המילים | `dev-plan` שלבים 7–8, `dev-code`, `dev-next` שלב 4, `chat-decisions.md`, `orchestrate.md`, `rank_issues.py` (`LEGACY_READY`), התרשים ושני העמודים |
| מחיקת branch אחרי מיזוג: ההגדרה של GitHub, בלי `--delete-branch`, ומה עושים כשהיא כבויה | `git-flow.md`, "מוסכמת branches ו-PR" | `dev-ship`, `dev-setup`, `cloud.md` (רק הפקודה ב-REST), `~/.claude/rules/env-cloud.md` |
| `costs-money`: מה היא עושה, מי מוסיף ומי מסיר | `pipeline.md`, אוצר המילים | `dependencies.md` (רק ההשפעה על הדירוג), `dev-plan`, `dev-next`, `dev-orchestrate`, `dev-setup` |
| משימה מושהית שדולב ביקש במספר: שאלה בחלון לפני כל צעד, הסיבה מ-`pause_reason.py`, שלוש האפשרויות, ובלי חלון לא מתחילים (S-1.44) | `chat-decisions.md`, "משימה מושהית שדולב ביקש במספר" | `pipeline.md` (שורת `paused`), `dev-plan` שלב 1, `dev-code` שלב 2, `dev-next` שלבים 1 ו-3, התרשים ושני העמודים |
| משימות המשך במסירה: שני הסוגים, הכותרת הקבועה `#### משימות המשך`, השדות, ומה קורה להצעה (S-1.47) | `follow-ups.md` | `process-tasks.md` (משימת תהליך), `chat-decisions.md` (ההחלטה הרביעית), `orchestrate.md` (החוזה, סעיף 4), `dev-code` שלבים 10–11, `dev-orchestrate` שלב 5, `follow_ups.py` (הפירוק והמפתח, S-2.16), `dev-issue`, התרשים ושני העמודים |
| הרצות חוזרות של תרחישים: אחת אחרי השנייה, ו"לא יציב": נכשל במלאה ועבר בחוזרת בלי שינוי, עם הפניה ל-issue פתוח או משימת המשך (S-1.61) | `tests.md`, "תרחישי הסקילים" | `dev-code` שלבים 7 ו-11, `follow-ups.md` |
| `priority:high`: מה היא עושה, איפה היא בסדר, ושהיא מושמת ומוסרת רק בהחלטה של דולב (S-1.62) | `pipeline.md`, אוצר המילים | `dependencies.md` (רק ההשפעה על הדירוג), `dev-next`, `dev-setup`, התרשים ושני העמודים |
| `paused`: מה היא עושה, ושהיא מושמת ומוסרת רק בהחלטה של דולב, והסיבה בתגובה `סיבת השהיה:` | `pipeline.md`, אוצר המילים | `dependencies.md` (רק ההשפעה על הדירוג), `dev-next`, `dev-orchestrate`, `dev-setup` |
| קוד ווב לפי Modern Web Guidance: מתי חל, הפקודות בגרסה הנעוצה, נתוני השימוש כבויים, סתירה לנוהל היא שאלה, הסריקה במסירה בלבד, ושורת `מדריכי ווב:` (S-4.16) | `web-guidance.md` | `dev-code` שלבים 5 ו-11, `settings.json` (`DISABLE_TELEMETRY` וכלל ההרשאה; הגרסה נבדקת ב-`test_web_guidance_pin.py`, והכלל עובר את `hooks/test_settings_permissions.py` כפקודה נעוצה), `~/.claude/rules/code-react.md` |

**עותק מכוון** מסומן בטבלה, ונשמר בבדיקה ולא ביד (`skills/dev-setup/scripts/test_doc_drift.py`, שבודקת גם ששני העמודים "חייו של issue" באותו מבנה, ושכל קובץ `.md` וכל סקיל שהמפה מונה קיימים). היום יש אחד: פקודות הבדיקה ב-`README.md`.
