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
| היקף הספרינט: סריקה לא יוצאת מה-milestone הנוכחי, issue שדולב נקב בשמו מותר, Claude לא משייך milestone (חוץ מבאג ו-`process` בפתיחה, ופירוק מהמתזמר) | `pipeline.md`, "ספרינטים" | `dev-plan`, `dev-code`, `dev-next`, `dev-issue` |
| הצעה בבקלוג ששויכה ל-milestone של הספרינט היא הצעה מאושרת: בן אפיון ראשון בתור, אחד בכל פעם, והפירוק שלה נכנס לספרינט שלה (S-2.14) | `specs.md`, "מתי נכתב אפיון" | `orchestrate-spec.md`, `pipeline.md` ("ספרינטים"), `dev-orchestrate`, `dev-spec` צעד 1, `dev-issue` ("פירוק אפיון"), `dev-plan` צעד 2 |
| שער ה-WIP: שלושה ומעלה ב-`status:in-review`, כולל PR שכבר נסקר; תיקון פטור; בן של המתזמר מדלג | `git-flow.md`, "כמה issues בריצה אחת" | `dev-code` שלב 1 (הפקודה), `orchestrate.md` (המתזמר בודק לפני בן קוד) |
| החלטה באה רק מדולב עצמו | `chat-decisions.md`, כלל 3 | `pipeline.md`, `dev-plan`, `dev-code`, `dev-ship` |
| עובדות הסביבה בענן: GraphQL חסום, push שמוחק branch חסום, הרשת דרך proxy | `~/.claude/rules/env-cloud.md` | `cloud.md`, `git-flow.md` |
| תרגום פקודות `gh` בענן | `cloud.md`, "פקודות GitHub בסשן ענן" | כל סקיל `dev-*` (שלב 0) |
| צעדי git בענן: ה-branch של המשימה, בלי worktree, החלפת branch בעץ נקי, הניקוי אחרי מיזוג, שם הסשן | `git-flow.md`, "בסשן ענן" | `~/.claude/rules/git.md` (החריג), `cloud.md`, `dev-ship` צעד 7 |
| פקודות הבדיקה של claude-config | `.claude/CLAUDE.md`, "בדיקות" | `README.md` מחזיק עותק מלא בכוונה. בדיקה משווה את שניהם ל-`tests.yml` (`skills/dev-setup/scripts/test_doc_drift.py`) |
| בדיקה ידנית בדפדפן וצילומי מסך: Edge, Playwright, הרוחבים, הצילומים למסירה | `ux.md` | `~/.claude/rules/code-tests.md`, `tests.md`, `~/.claude/rules/env-windows.md` (רק עובדות Edge), `~/.claude/rules/env-cloud.md`, `dev-code` שלב 10 |
| פרסום מחדש של עמוד Artifact אחרי מיזוג: קריאה, השוואה, `publish` בלי `icon` ובלי `force`, השלד | `after-merge.md`, "פרסום מחדש של עמוד Artifact" | `.claude/CLAUDE.md` של claude-config (העמודים והקישורים), `~/.claude/rules/erd.md`, `dev-ship` |
| אות המיזוג: בקשה אחת של דולב בצ'אט, על ה-issue הספציפי | `pipeline.md`, "הכללים שלא משתנים" | `chat-decisions.md` כלל 7, `dev-code`, `dev-ship` |
| ארבעת התנאים של משימה קטנה | `pipeline.md`, "המסלול הקטן" | `dev-plan` שלב 7, `dev-code` שלב 8 |
| issue אחד בכל ריצת קוד | `git-flow.md`, "כמה issues בריצה אחת" | `dev-code`, `dev-next`, `after-merge.md` |
| מחיקת branch אחרי מיזוג: ההגדרה של GitHub, בלי `--delete-branch`, ומה עושים כשהיא כבויה | `git-flow.md`, "מוסכמת branches ו-PR" | `dev-ship`, `dev-setup`, `cloud.md` (רק הפקודה ב-REST), `~/.claude/rules/env-cloud.md` |
| `costs-money`: מה היא עושה, מי מוסיף ומי מסיר | `pipeline.md`, אוצר המילים | `dependencies.md` (רק ההשפעה על הדירוג), `dev-plan`, `dev-next`, `dev-orchestrate`, `dev-setup` |
| `paused`: מה היא עושה, ושרק דולב שם ומסיר | `pipeline.md`, אוצר המילים | `dependencies.md` (רק ההשפעה על הדירוג), `dev-next`, `dev-orchestrate`, `dev-setup` |

**עותק מכוון** מסומן בטבלה, ונשמר בבדיקה ולא ביד (`skills/dev-setup/scripts/test_doc_drift.py`, שבודקת גם ששני העמודים "חייו של issue" באותו מבנה, ושכל קובץ `.md` וכל סקיל שהמפה מונה קיימים). היום יש אחד: פקודות הבדיקה ב-`README.md`.
