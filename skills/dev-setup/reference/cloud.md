# עבודה מסשן ענן ומהטלפון

שתי דרכים לעבוד בלי לשבת מול המחשב. הקובץ הזה הוא בשביל דולב, ובשביל סקיל שצריך לדעת איפה הוא רץ.

## מה הבעיה
סשן ענן רץ ב-container נקי: מחשב זמני שמוקם מאפס לכל סשן, ונמחק בסופו.
את התיקייה `~/.claude` שלו מקים שירות הענן של Claude Code, המערכת של Anthropic שמריצה את הסשן, ולא הריפו הזה.
השירות שם בה קבצים משלו: `launcher-settings.json` (ההגדרות שלו לכל סשן), `plugins/` ו-`skills/synced/` (התוספים והסקילים מהחשבון ב-claude.ai), ו-`environment-manager/` (מצב ההקמה). את חלקם הוא חוסם לעריכה.
בלי התקנה, בסשן ענן של כל ריפו לא נטענים `CLAUDE.md` הגלובלי, `rules/`, הסקילים `dev-*`, ה-hooks ו-`settings.json`.
מזהים סשן ענן לפי `CLAUDE_CODE_REMOTE=true` בסביבה.

## דרך 1: Remote Control (בלי התקנה)
הסשן רץ על המחשב, ודולב שולט בו מהטלפון באפליקציית Claude. הכל עובד כמו היום.
- **מה צריך:** המחשב דולק, ו-Claude Desktop פתוח.
- **איך מפעילים:** ב-Claude Desktop פותחים Settings, אחר כך Claude Code, אחר כך Remote Control, ובוחרים את התיקיות.
  דרך אחרת: `claude remote-control` בטרמינל, בתיקייה של הפרויקט.
- **מתי לבחור בה:** כשהעבודה צריכה את המחשב. למשל כלי של Windows, או אפליקציה לסקירה שהפקודה שלה ל-Windows בלבד (`review-app.md`).

## דרך 2: סשן ענן מלא
הסשן רץ בענן, גם כשהמחשב כבוי.
אחרי ההגדרה החד-פעמית, כל סשן בסביבה עולה עם ההגדרות של הריפו הזה, בגרסה של `main`.

### הגדרה חד-פעמית
1. **הריפו `dolev2/claude-config` ציבורי.** סשן ענן מקבל הרשאה רק לריפואים שנבחרו לו, ולכן בסשן על פרויקט ריפו פרטי אחר חסום, גם כשהוא ברשימת ה-Repositories של הסביבה (נבדק ב-5.11.2026). ריפו ציבורי נגיש מכל סשן. קבצים רגישים לא נכנסים לריפו (`.gitignore`).
2. **יוצרים סביבה משלך** (הסביבה של דולב: `dolev cloud`).
   בסשן ענן: התפריט של הסביבה בשורת הכותרת של הסשן, ואז יצירה של סביבה חדשה (או Edit לסביבה קיימת).
3. **מדביקים בשדה Setup script את הסקריפט מהסעיף הבא**, כמו שהוא.
4. **בוחרים את הסביבה הזו בכל סשן חדש**, בכל ריפו.

### סקריפט ההתקנה
הסקריפט הופך את `~/.claude` של ה-container לעותק של `main`, בדיוק כמו במחשב.
הקבצים של השירות שכבר שם (`launcher-settings.json`, `plugins/`, `skills/synced/`) נשארים: ה-`.gitignore` מתעלם מהם, ו-`checkout` לא נוגע בהם.
הנתיבים `$HOME/.claude/...` בסקילים וב-hooks עובדים בלי שינוי, ו-`guard_main_folder.py` שומר על התיקייה גם בענן.
כשיש ב-`~/.claude` שינויים שלא נשמרו, הוא לא נוגע בהם.
**הסקריפט אף פעם לא נכשל.** סקריפט התקנה שנכשל עוצר את כל הסשן (נבדק ב-5.11.2026), ולכן כשההתקנה לא מצליחה הוא רק כותב אזהרה, והסשן עולה בלי ההגדרות.

<!-- setup-script: test_cloud_setup.py runs this block as is -->
```bash
REPO=https://github.com/dolev2/claude-config
# Never exits non-zero: a failing setup script stops the whole session (#132).
(
  set -e
  export GIT_TERMINAL_PROMPT=0
  mkdir -p ~/.claude
  cd ~/.claude
  if git rev-parse -q --verify HEAD >/dev/null 2>&1 && [ -n "$(git status --porcelain)" ]; then
    echo "~/.claude has uncommitted changes: not updating it" >&2
    exit 1
  fi
  git init -q
  git remote add origin "$REPO" 2>/dev/null || git remote set-url origin "$REPO"
  git fetch -q --depth 1 origin main
  git checkout -q -f -B main FETCH_HEAD
) || echo "claude-config was not installed in ~/.claude" >&2
```

**רק לסביבת ענן.** במחשב `~/.claude` כבר מותקן, ולא מריצים את הסקריפט שם.

### עדכון בכל סשן
השירות מריץ את סקריפט ההתקנה פעם אחת, שומר תמונה של הדיסק, וממחזר אותה כנקודת התחלה עד כשבעה ימים. בלי עדכון, `~/.claude` יכול לפגר אחרי `main` עד שבוע.
לכן `hooks/cloud_refresh.py` (SessionStart, ב-`settings.json`) מושך את `main` בתחילת כל סשן ענן. במחשב הוא לא עושה כלום, כי `CLAUDE_CODE_REMOTE` לא מוגדר שם. כשב-`~/.claude` יש שינויים שלא נשמרו, הוא לא נוגע בהם.
**באמצע סשן, `--report`:** המתזמר מריץ אותו כשמוזג שינוי בצינור. הוא מדפיס `refreshed <sha>` (יציאה 0) או `not refreshed: <reason>` (יציאה 1). הסיבות ב-docstring של הסקריפט, והשימוש ב-`orchestrate.md`, "שינוי בצינור באמצע ספרינט".
**`settings.json` באמצע סשן** (נבדק ב-9.11.2026, #192): כלל הרשאות שנוסף חל אחרי כמה שניות. רישום של hook חדש לא נבדק, כי מצב auto חסם את העריכה (Self-Modification). לכן `settings.json` נשאר ב-`SESSION_PATHS` של `pipeline_shas.py`, עד שגם הרישום ייבדק.

### איך בודקים שזה עובד
בסשן ענן חדש, בריפו של פרויקט:
1. `dev-next` מופיע ברשימת הסקילים.
2. התשובה הראשונה בעברית, במבנה של `CLAUDE.md`.
3. `git push --force` נחסם על ידי `block_force_push.py`.

### כשההתקנה נכשלת
הסשן עולה בכל זאת, בלי ההגדרות: אין `dev-*` ברשימת הסקילים, והתשובות לא במבנה של `CLAUDE.md`.
- **אין גישה לריפו** (`could not read Username`): `dolev2/claude-config` הפך לפרטי. סשן על פרויקט לא מקבל גישה לריפו פרטי אחר.
- **שינויים שלא נשמרו ב-`~/.claude`**: מישהו ערך שם קובץ בסשן קודם באותו container. מסתכלים על `git -C ~/.claude status`, ולא מוחקים בלי לבדוק.

## פקודות GitHub בסשן ענן
סקיל שרץ בסשן ענן (`CLAUDE_CODE_REMOTE=true`) מריץ כל פקודת `gh` שלו דרך הטבלה הזו (נבדקה בענן ב-6.11.2026, claude-config #139):
1. **GraphQL חסום (403).** לכן `gh issue`, `gh pr`, `gh label`, `gh repo view`, `gh repo edit`, `gh project` ו-`gh api graphql` לא רצים.
2. **REST עובד, רק לריפואים שחוברו לסשן**, וגם הכלים `mcp__github__*`. בטבלה `R` הוא `repos/{owner}/{repo}`: `gh api` ממלא אותו מה-remote. ריפו אחר מחזיר 403, גם כשהוא ציבורי. claude-config נקרא מסשן של ריפו אחר דרך git אנונימי (`cloud_refresh.py`, `sprint_state.py`, #211).
3. **כתיבת גוף** (issue, תגובה, PR): ב-`--input <file>`, כמו בטבלה. הכלל המלא: `issue-body.md`, "עריכת הגוף".
4. **השירות מוסיף footer לכל גוף ולכל תגובה** שנכתבים מהענן: `---`, ואחריו `_Generated by [Claude Code](...)_`.
   שער השאלות מדלג עליו (claude-config #142).
5. **רשימה רצה עם `--paginate`** (תוויות, issues, תגובות, timeline). בלעדיו GitHub מחזיר רק את העמוד הראשון, 30 פריטים.
6. **REST מחזיר ערכים בצורה אחרת מ-`--json`:** `.state` הוא `open` או `closed` (PR שמוזג: `.merged` הוא `true`), ו-`.mergeable` הוא `true`, `false` או `null` (עוד מחושב: שואלים שוב). `--jq` שמשווה ל-`"OPEN"` או ל-`"MERGEABLE"` מתורגם בהתאם.
   השדות `number`, `title`, `body` ו-`state` נקראים באותו שם ב-REST. `url` לא: ב-REST `.url` היא כתובת ה-API, וכתובת הדף היא `.html_url`.
   שדה חדש ב-`--json` של סקיל נכנס לכאן או לטבלה, אחרת `test_cloud_table_covers_every_json_field` נכשלת.

| הפקודה | בסשן ענן |
|---|---|
| `gh issue view <N>` (`--json body,labels,title`) | `gh api R/issues/<N>` |
| `gh issue view <N> --comments` | `gh api R/issues/<N>/comments` |
| `gh issue view --json closedByPullRequestsReferences` | `gh api R/issues/<N>/timeline`: אירועי `cross-referenced` שה-`source.issue` שלהם PR, ואז `R/pulls/<P>` (פתוח, ו-`Closes #<N>` בגוף) |
| `gh issue edit --add-label` / `--remove-label` | `gh api -X POST R/issues/<N>/labels -f "labels[]=<a>" -f "labels[]=<b>"` (שדה לכל תווית), ו-`gh api -X DELETE R/issues/<N>/labels/<l>`, קריאה לכל תווית שמוסרים |
| `gh issue edit --body-file` | `gh api -X PATCH R/issues/<N> --input <file>` |
| `gh issue create` | `gh api -X POST R/issues --input <file>`. ה-milestone במספר שלו (`R/milestones`), לא בשם |
| `gh issue comment`, `gh pr comment` | `gh api -X POST R/issues/<N>/comments --input <file>` |
| `gh issue list --milestone` | `rank_issues.py`. רשימה לפי תווית: `R/issues?state=open&labels=<l>`, בלי מה שיש לו `pull_request` |
| `gh label list` / `create` / `edit` | `gh api R/labels`, `-X POST R/labels`, `-X PATCH R/labels/<l>` |
| `gh repo view` / `gh repo edit` | `pipeline_info.py`. `--json visibility`: `gh api R --jq .visibility` (`public` / `private`). `gh repo edit --delete-branch-on-merge`: `gh api -X PATCH R -F delete_branch_on_merge=true`. מה עושים כשהוא חוזר 403: `git-flow.md` |
| `gh pr create` / `gh pr edit` | `mcp__github__create_pull_request` / `mcp__github__update_pull_request` |
| `gh pr view` (`--json state,headRefName,headRefOid,mergeable,mergeStateStatus`) | `gh api R/pulls/<N>`: `.state` ו-`.merged`, `.head.ref`, `.head.sha`, `.mergeable`, `.mergeable_state` (`clean`, `dirty`, `behind`, `blocked`, `unstable`). `MERGEABLE` הוא `.mergeable == true` |
| `gh pr view --json closingIssuesReferences` | אין שדה כזה ב-REST: ה-issues מה-`Closes #<N>` ב-`.body` של `R/pulls/<N>` |
| `gh pr list` (`--head`, `--state`, `--search`) | `gh api "R/pulls?state=open&head=<owner>:<branch>"` (`state` כמו ב-`--state`: `open`, `closed` או `all`). חיפוש לפי issue: ה-timeline, כמו בשורה של `closedByPullRequestsReferences` |
| `gh pr checks --watch` | `subscribe_pr_activity`, ומסיימים את התור: האירוע `check_suite.completed` מעיר את הסשן. אחריו, ולבדיקה חד-פעמית: `gh api R/commits/<sha>/check-runs` |
| `gh pr merge --squash` | `mcp__github__merge_pull_request` עם `merge_method: "squash"` ו-`expectedHeadSha`, בלי `commit_title`. `hooks/ask_before_merge.py` מקפיץ חלון אישור לפני כל מיזוג (claude-config #135). את ה-branch ב-GitHub מוחקת ההגדרה של הריפו, כמו מחוץ לענן (`git-flow.md`) |
| ה-GraphQL של `issue-body.md` (sub-issues ומי שמפנה) | `gh api R/issues/<N>/sub_issues`, ו-`R/issues/<N>/timeline` (אירועי `cross-referenced`) |
| Blocked by ו-sub-issue (`dependencies.md`, `dev-issue`) | כבר REST: רצים כמו שהם |

**מה חסום גם ב-REST:** `PROJECT_NUMBER` (משתנה של Actions), הלוח (`gh project`, `projectItems`) ו-`dev-setup` בענן: claude-config #140. גם הכתיבה ל-rulesets חסומה ב-proxy (403), והקריאה עובדת (claude-config #162). מ-`dev-setup` כבר עובדת רק הקריאה של `issue_forms` כשהוא `unknown`.

## חלונות אישור בסשן-בן
סשן-בן שמחכה לאישור לא נראה תקוע מבחוץ, ומתזמר יחכה לו בלי סוף (claude-config #155). לכן:
1. **מאושר מראש** (`permissions.allow` ב-`settings.json`): כלי קריאה של GitHub, וכלים שנוגעים רק בסשן עצמו (`get_session`, `list_events`, `set_session_title`, `subscribe_pr_activity` ודומיהם).
   חריג קטן: `set_session_title` יכול לשנות גם שם של סשן אחר בחשבון, לפי ה-`session_id`. הוא ברשימה כי הנזק רק שם, ומשנים אותו בחזרה.
   הרשימה חלה גם במחשב: כלי `mcp__claude-code-remote__` לא קיימים שם, וכלי GitHub ברשימה קוראים, חוץ משלושת הכותבים של החריג השני.
   הבדיקה `hooks/test_settings_permissions.py` שומרת עליה: שמות מלאים בלבד, בלי `*`, ורק מתוך הרשימה שבבדיקה.
   חריג שני: שלושת הכלים שהבן של המתזמר צריך (`CHILD_TOOLS` ב-`hooks/guard_create_session.py`: פתיחת PR, עדכון PR, תגובה ב-issue). הם מאושרים מראש כדי שיעברו לבן (סעיף 5, #150).
2. **תמיד שואל:** כל כלי אחר שכותב מחוץ לסשן (issue, קובץ ב-GitHub), `send_later` ו-`create_trigger` (שומרים משימה מתוזמנת בחשבון), `create_session`, `archive_session` ו-`interrupt_session`.
   גם בקשה שהשירות מסמן `server_policy_ask_only: true` שואלת, ושום כלל לא עוקף אותה.
   **השירות מכריח חלון ל-`create_session`, ל-`archive_session` ול-`send_message` של סשן-בן, ושום כלל לא עוקף אותו** (claude-config #179, #184).
   החלון שלהם מגיע עם `decision_reason_type: "other"` ו-`suppress_always_allow_rule: true`, ולכן אין בו "אשר תמיד".
   נבדק ב-8.11.2026: `archive_session` ב-`permissions.allow` של ה-container, והחלון קפץ בכל זאת.
   גם `send_message` של סשן-בן להורה, נבדק ב-8.11.2026 עם אותו סימון. הכיוון ההפוך, מהמתזמר לבן, לא נבדק. לכן בן לא שולח הודעות: הוא מדווח ב-GitHub, והמתזמר מושך (`orchestrate.md`, "איך המתזמר יודע שבן התקדם").
   לכן הם לא נכנסים ל-`permissions.allow`: כלל שם לא היה משנה כלום.
   **בדיקה ברקע לא מקפיצה חלון:** `gh api` ב-Bash עם `run_in_background` וב-Monitor רצו בסשן-בן בלי חלון, והיציאה העירה סשן שכבר סיים את התור. נבדק ב-8.11.2026.
   `interrupt_session`: לא נבדק אם השירות מכריח חלון גם לו.
3. **מיזוג שואל תמיד:** hook שמחזיר `ask` (`ask_before_merge.py`) גובר על אישור מראש. נבדק בענן ב-6.11.2026.
4. **איך מזהים סשן-בן תקוע** (`get_session`): `session_status` הוא `SESSION_STATUS_REQUIRES_ACTION`, `status_bucket` הוא `SESSION_STATUS_BUCKET_BLOCKED`, ו-`external_metadata.pending_actions` מראה את הכלי ואת הקלט שלו.
   גם בקשה של סוכן-משנה (`Agent`) חוסמת את כל הסשן.
   **הערך `SESSION_STATUS_BUCKET_BLOCKED` לבדו לא מספיק:** בן שסיים את התור ומחכה להחלטה מראה אותו גם כן, עם `SESSION_STATUS_IDLE` ובלי `pending_actions` (נבדק ב-8.11.2026, #189).
   תקוע הוא רק `pending_actions` לא ריק או `SESSION_STATUS_REQUIRES_ACTION` (`orchestrate.md`, "מצב בן").
5. **מתזמר שפותח סשן-בן** מעביר את כלי הכתיבה שהבן צריך (`CHILD_TOOLS`, מאושרים מראש לפי החריג השני) ב-`extra_allowed_tools` של `create_session`.
   השירות מעביר לבן רק כלים שמאושרים מראש אצל מי שפתח אותו. זה גיבוי, לא תחליף לרשימה.
   **hook מקפיץ חלון אישור** (`hooks/guard_create_session.py`, claude-config #175) כשהבן מקבל יותר מזה:
   1. כלי ב-`extra_allowed_tools` שלא ברשימת `CHILD_TOOLS` שב-hook (פתיחת PR, עדכון PR, תגובה ב-issue). גם `send_message`, שיצא מהרשימה ב-#184. זה תופס `Bash(...)`, `*` וכל כלי כתיבה אחר.
   2. `environment_id` מוגדר: הבן ייפתח בסביבה אחרת, עם רשת והרשאות אחרות. גם בן של מתזמר בלי תגית `repo:` שתואמת ל-`source_url` מקפיץ חלון (`orchestrate.md`, "פתיחת בן", #217).

   החלון מונה מה בדיוק עובר לבן. דחייה: הסשן לא נפתח.
   איך המתזמר פותח בן, והחוזה שעובר אליו: `orchestrate.md`.
6. **שם הסשן**, `<repo>: <branch>`, נקבע ב-`title` של `create_session`, והבן לא קורא ל-`set_session_title` (`git-flow.md`, "בסשן ענן").
   בסשן-בן, `set_session_title` מקפיץ חלון למרות שהוא ב-`permissions.allow` (נבדק ב-8.11.2026, #184). לכן החוזה אוסר על הבן כל כלי של `claude-code-remote` (`orchestrate.md`, סעיף 8).

## מה עוד שונה בסשן ענן
GraphQL חסום (עובדות הסביבה: `rules/env-cloud.md`): הסקריפטים קוראים רק דרך REST (claude-config #138), והסקילים עובדים דרך הטבלה בסעיף "פקודות GitHub בסשן ענן".

ה-branch, ה-worktree, הניקוי אחרי מיזוג ושם הסשן: `git-flow.md`, הסעיף "בסשן ענן" (claude-config #134).

כללי Windows ב-`rules/env-windows.md` לא חלים בענן, חוץ מהסעיף "מה חייב לעבוד גם מחוץ ל-Windows". מה מותקן בענן, ומה נשאר למחשב: `rules/env-cloud.md` (claude-config #136).
הבדיקה הוויזואלית בענן היא צילומי מסך ב-Playwright (`ux.md`), והאפליקציה לסקירה עולה בתוך הסשן (`review-app.md`).
