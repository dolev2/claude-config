# claude-config

נהלי העבודה של דולב עם Claude Code, במקום אחד. התיקייה הזו היא `~/.claude`.

| מה | איפה | מתי נטען |
|---|---|---|
| ההנחיות הגלובליות | `CLAUDE.md` | בכל סשן, בכל פרויקט |
| כללים לכל הפרויקטים | `rules/` | בכל סשן, בכל פרויקט |
| הסקילים | `skills/` | בכל סשן, בכל פרויקט |
| ההנחיות לעבודה על הריפו הזה | `.claude/CLAUDE.md` | רק בסשן שעובד בתוך הריפו |

ה-`.gitignore` חוסם הכל ומתיר רק את מה שמפורט בו. פרטי ההתחברות, התמלולים והזיכרון של הפרויקטים לא נכנסים לריפו.

| סקיל | מה עושה |
|---|---|
| `dev-issue` | פותח issues ומפרק משימות |
| `dev-next` | בוחר את המשימה הבאה בספרינט |
| `dev-plan` | שלב התכנון |
| `dev-code` | שלב הביצוע וה-merge |
| `dev-ship` | שחרור branch מההתחלה ועד הסוף |
| `dev-setup` | מתקין את הצינור בריפו חדש. מחזיק גם את המסמך המשותף (`reference/pipeline.md`), הסקריפטים, ה-actions המשותפים והתבניות |

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
