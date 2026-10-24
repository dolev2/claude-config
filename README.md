# claude-skills

הסקילים האישיים של Claude Code, שזמינים בכל פרויקט. התיקייה הזו היא `~/.claude/skills`.

| סקיל | מה עושה |
|---|---|
| `dev-issue` | פותח issues ומפרק משימות |
| `dev-next` | בוחר את המשימה הבאה בספרינט |
| `dev-plan` | שלב התכנון |
| `dev-code` | שלב הביצוע וה-merge |
| `dev-ship` | שחרור branch מההתחלה ועד הסוף |
| `dev-setup` | מתקין את הצינור בריפו חדש. מחזיק גם את המסמך המשותף (`reference/pipeline.md`), הסקריפטים והתבניות |

## במחשב חדש

```bash
git clone https://github.com/dolev2/claude-skills.git ~/.claude/skills
```

## בדיקות

```bash
python -m pytest ~/.claude/skills/dev-setup/scripts
```
