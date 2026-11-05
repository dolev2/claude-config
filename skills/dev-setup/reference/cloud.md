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
- **מתי לבחור בה:** כשהעבודה צריכה את המחשב. למשל הרמה לסקירה (`review-app.md`), או כלי של Windows.

## דרך 2: סשן ענן מלא
הסשן רץ בענן, גם כשהמחשב כבוי.
אחרי ההגדרה החד-פעמית, כל סשן בסביבה עולה עם ההגדרות של הריפו הזה, בגרסה של `main`.

### הגדרה חד-פעמית
1. **יוצרים סביבה משלך.** בסביבת ברירת המחדל (Default) אין רשימת Repositories, ולכן אין לה גישה לריפו פרטי.
   בסשן ענן: התפריט של הסביבה בשורת הכותרת של הסשן, ואז יצירה של סביבה חדשה (או Edit לסביבה קיימת).
2. **מוסיפים לה את `dolev2/claude-config` ברשימת ה-Repositories.** כך לסקריפט ההתקנה יש גישה לריפו.
3. **מדביקים בשדה Setup script את הסקריפט מהסעיף הבא**, כמו שהוא.
4. **בוחרים את הסביבה הזו בכל סשן חדש**, בכל ריפו.

### סקריפט ההתקנה
הסקריפט הופך את `~/.claude` של ה-container לעותק של `main`, בדיוק כמו במחשב.
הקבצים של השירות שכבר שם (`launcher-settings.json`, `plugins/`, `skills/synced/`) נשארים: ה-`.gitignore` מתעלם מהם, ו-`checkout` לא נוגע בהם.
הנתיבים `$HOME/.claude/...` בסקילים וב-hooks עובדים בלי שינוי, ו-`guard_main_folder.py` שומר על התיקייה גם בענן.
כשיש ב-`~/.claude` שינויים שלא נשמרו, הוא עוצר ולא נוגע בהם.

<!-- setup-script: test_cloud_setup.py runs this block as is -->
```bash
set -e
REPO=https://github.com/dolev2/claude-config
mkdir -p ~/.claude
cd ~/.claude
if [ -d .git ] && [ -n "$(git status --porcelain)" ]; then
  echo "~/.claude has uncommitted changes: not updating it" >&2
  exit 1
fi
git init -q
git remote add origin "$REPO" 2>/dev/null || git remote set-url origin "$REPO"
git fetch -q --depth 1 origin main
git checkout -q -f -B main FETCH_HEAD
```

**רק לסביבת ענן.** במחשב `~/.claude` כבר מותקן, ולא מריצים את הסקריפט שם.

### איך בודקים שזה עובד
בסשן ענן חדש, בריפו של פרויקט:
1. `dev-next` מופיע ברשימת הסקילים.
2. התשובה הראשונה בעברית, במבנה של `CLAUDE.md`.
3. `git push --force` נחסם על ידי `block_force_push.py`.

### כשההתקנה נכשלת
הסשן עולה בכל זאת, ושירות הענן מודיע ל-Claude שהסקריפט נכשל ובאיזה קוד יציאה.
Claude אומר לדולב בשורה אחת מה נכשל, וממשיך בלי הסקילים.
- **אין גישה לריפו** (`fetch` נכשל): `dolev2/claude-config` חסר ברשימת ה-Repositories של הסביבה, או שהסשן נפתח בסביבה אחרת.
- **שינויים שלא נשמרו ב-`~/.claude`**: מישהו ערך שם קובץ בסשן קודם באותו container. מסתכלים על `git -C ~/.claude status`, ולא מוחקים בלי לבדוק.

## מה עוד שונה בסשן ענן
אלה משימות פתוחות, וכל אחת מעדכנת את הקובץ הזה כשהיא נסגרת:
1. GraphQL חסום, ולכן `gh issue`, `gh pr` ו-`gh project` נכשלים. `gh api repos/...` (REST) עובד (claude-config #133).
2. הסשן מקבל branch משלו, ואין צורך ב-worktree (claude-config #134).
3. חלון האישור לפני merge תופס רק את `gh pr merge` (claude-config #135).
4. כללי Windows ב-`rules/env-windows.md` לא חלים בענן (claude-config #136).
