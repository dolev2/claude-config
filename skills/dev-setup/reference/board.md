# לוח ה-Project בהתקנה

`dev-setup`, שלבים 4 ו-5, מתקין לפי הקובץ הזה.
למה הלוח עובד כמו שהוא עובד (הסנכרון בכיוון אחד, המוקשים של ה-API): `setup.md`.
בלי לוח הצינור עובד בכל זאת: התוויות הן מקור האמת. אז מדלגים על הקובץ הזה ועל `sync-project.yml`, והשער נשאר.

## הסנכרון המתוזמן מרכזי
כרטיס שנגרר בלוח חוזר לעמודה של התווית שלו רק דרך סקר כל 15 דקות.
הסקר רץ פעם אחת לכל הריפואים, מהריפו הציבורי dolev2/.github (`sync-boards.yml`, שמריץ את `actions/project-sync/sweep_all.py`), שם דקות ה-Actions בחינם.
כשהוא רץ בכל ריפו פרטי, הוא גמר את 2,000 הדקות של החשבון (אוקטובר 2026, #46).
לכן ל-`sync-project.yml` בריפו יש רק אירועי issue, אף פעם לא `schedule`. הריצה המרכזית מוצאת ריפו חדש לפי המשתנה `PROJECT_NUMBER` שלו.
היא גם משווה את מספר הלוחות שמצאה למשתנה `EXPECTED_BOARDS` של dolev2/.github, ונכשלת על כל מספר אחר (#49).
לכן ההתקנה מעדכנת את המספר. גם העברה לארכיון של ריפו עם לוח: הריצה נשארת אדומה עד שמעדכנים.

## יצירה וקישור (שלב 4)
```bash
OWNER=$(gh repo view --json owner --jq .owner.login)
gh project create --owner "$OWNER" --title "<Title>" --format json --jq .number
gh project link <number> --owner "$OWNER" --repo "$OWNER/<repo>"
gh project field-create <number> --owner "$OWNER" --name Area --data-type SINGLE_SELECT \
  --single-select-options "Backend,Frontend,Both,Infra"   # the agreed areas' option texts
gh variable set PROJECT_NUMBER --body <number>
```

אחר כך מעדכנים את מספר הלוחות שהריצה המרכזית מצפה לו. סופרים אותם, אף פעם לא מוסיפים 1: ריצה שנייה על אותו ריפו הייתה סופרת אותו פעמיים.
הספירה רצה ב-`gh` של דולב עצמו, שרואה כל ריפו. token שרואה פחות מדי הוא בדיוק מה שהמספר שומר מפניו.

```bash
N=$(python "$HOME/.claude/skills/dev-setup/actions/project-sync/sweep_all.py" --owner "$OWNER" --count-boards)
gh variable set EXPECTED_BOARDS --repo "$OWNER/.github" --body "$N"
```

הטקסטים של אפשרויות Area הולכים לפי כלל אחד: הסיומת של התווית, באות ראשונה גדולה; ראשי תיבות נשארים באותיות גדולות, ולכן `area:seo` הוא `SEO`.
הסנכרון מתאים תוויות לאפשרויות לפי הכלל הזה, ולכן שום דבר אחר לא מונה את האזורים.

`gh project` צריך את ה-scope `project`. נדחה: מבקשים מדולב להריץ `gh auth refresh -s project`, ומחכים.

## שדה Status
**Status הוא השדה המובנה**, ולכן לא יוצרים אותו אלא כותבים אותו מחדש.
האפשרויות שלו חייבות להתאים בדיוק ל-`STATUS_OPTIONS` ב-`dev-setup/actions/project-sync/sync_rules.py`. מוצאים את ה-id שלו, ואז מחליפים את האפשרויות:

```bash
gh api graphql -f query='query($o:String!,$n:Int!){user(login:$o){projectV2(number:$n){field(name:"Status"){... on ProjectV2SingleSelectField{id}}}}}' \
  -F o="$OWNER" -F n=<number> --jq .data.user.projectV2.field.id
```

כותבים את זה לקובץ, ושולחים ב-`gh api graphql --input <file>`:

```json
{"query": "mutation($id:ID!,$opts:[ProjectV2SingleSelectFieldOptionInput!]){updateProjectV2Field(input:{fieldId:$id,singleSelectOptions:$opts}){projectV2Field{... on ProjectV2SingleSelectField{options{name}}}}}",
 "variables": {"id": "<field id>", "opts": [
  {"name": "Explore (Claude)", "color": "BLUE", "description": ""},
  {"name": "Plan questions", "color": "ORANGE", "description": ""},
  {"name": "Waiting for Dolev approval", "color": "YELLOW", "description": ""},
  {"name": "Ready to execute (Claude)", "color": "GREEN", "description": ""},
  {"name": "Needs repair (Claude)", "color": "RED", "description": ""},
  {"name": "Claude done / In review (Dolev)", "color": "PURPLE", "description": ""},
  {"name": "Done", "color": "GREEN", "description": ""},
  {"name": "Backlog", "color": "GRAY", "description": ""}]}}
```

ה-mutation נדחה: נותנים לדולב את שמונת השמות להקליד בהגדרות השדה בלוח.

## ה-token
**ה-token הוא צעד של דולב, אף פעם לא של Claude.** ה-workflow של הסנכרון צריך PAT עם `project` ו-`repo` ב-secret בשם `PROJECT_TOKEN`.
נותנים לדולב את הפקודה להריץ בעצמו, בשתי הגרסאות, והוא מעתיק את זו שמתאימה למחשב שלו. לא מבקשים ממנו להדביק את ה-token בצ'אט.

PowerShell (Windows):
```powershell
$t = Read-Host 'Paste token'; gh secret set PROJECT_TOKEN --body $t; Remove-Variable t
```

bash (Linux ו-macOS):
```bash
read -rs t; gh secret set PROJECT_TOKEN --body "$t"; unset t
```

`-s` כדי שה-token לא יופיע על המסך, והמרכאות כדי שתו מיוחד בו לא יתפרק. `unset` ו-`Remove-Variable` מוחקים אותו מה-shell.
אותן שתי שורות מופיעות בהודעת השגיאה של `sync_project.py` כש-`GH_TOKEN` ריק.

## התצוגות (סוף שלב 5)
התצוגות באות אחרי ה-milestones: תצוגת הספרינט מסננת לפי אחד מהם.

```bash
python "$HOME/.claude/skills/dev-setup/scripts/board_views.py" --dry-run
python "$HOME/.claude/skills/dev-setup/scripts/board_views.py"
```

הסקריפט הופך את "View 1" הריק של הלוח ל"ספרינט נוכחי" (עמודות לפי Status, מסונן לספרינט הנוכחי), ומוסיף את "הכל" (טבלה).
הוא לא מוחק כלום, ומדלג על תצוגה שכבר קיימת.
הוא מדווח שלתצוגת הספרינט אין עמודות: מבקשים מדולב לבחור "Column by: Status" בלוח; ה-API לא יכול לקבוע את זה.
מכאן והלאה הסנכרון של הלוח מזיז את הסינון לכל ספרינט הבא בעצמו (`setup.md`).
