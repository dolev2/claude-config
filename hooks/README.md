# hooks

השומרים: סקריפטים ש-Claude Code מריץ לפני פעולה או אחריה, כדי לאכוף כללים כתובים.
כל hook מחובר ב-`settings.json` באותה צורה, והחוזה שלו (JSON ב-stdin, יציאה 0 או 2) כתוב ב-[.claude/CLAUDE.md](../.claude/CLAUDE.md).
אם Python חסר, ה-hook לא חוסם, בכוונה.

## מדריך קבצים

משפט לכל קובץ.
הבדיקות, `test_*.py`, יושבות ליד הקובץ שהן בודקות, ו-`test_settings_permissions.py` שומר על רשימת ההרשאות ב-`settings.json`.

### ה-hooks
| קובץ | מה הוא |
|---|---|
| `block_force_push.py` | חוסם `git push --force` ודומיו, כי הם דורסים בשקט commits של מישהו אחר. |
| `block_merge_subject.py` | חוסם מיזוג עם כותרת commit שנכתבה ביד, כדי שהכותרת תילקח מכותרת ה-PR. |
| `ask_before_merge.py` | מקפיץ חלון אישור לפני מיזוג של PR שדולב לא ביקש בהודעה האחרונה שלו. |
| `guard_main_folder.py` | חוסם בתיקייה הראשית של `~/.claude` עריכה של קבצי הריפו ופקודות git שמחליפות branch או מוחקות עבודה. |
| `guard_parallel_parts.py` | חוסם סוכן בעבודה במקביל מלערוך קובץ מחוץ לחלק שלו. |
| `guard_create_session.py` | מקפיץ חלון אישור לפני פתיחת סשן-בן עם כלים, סביבה או תגית שלא תואמים לחוזה של המתזמר. |
| `ps1_bom.py` | מוסיף BOM לקובץ `.ps1` אחרי עריכה, כדי ש-PowerShell 5.1 יקרא עברית נכון. |
| `ruff_on_edit.py` | מריץ `ruff format` על קובץ Python אחרי עריכה, ומחזיר ל-Claude את שגיאות ה-lint שנשארו. |
| `cloud_refresh.py` | מעדכן את `~/.claude` ל-`main` בתחילת כל סשן ענן, כי התמונה של המחשב יכולה להיות ישנה. |
| `compact_after_merge.py` | דואג שאחרי מיזוג ההודעה האחרונה של התור תיגמר בבלוק `/compact` מלא. |

### הקוד המשותף
| קובץ | מה הוא |
|---|---|
| `merge_request.py` | קורא מהתמליל את ההודעה האחרונה של דולב, בשביל `ask_before_merge.py`. |
| `shell_commands.py` | קריאת הקלט, הקובץ שעריכה כותבת, וזיהוי של פקודת `gh` או `git` שממזגת. |
| `shell_split.py` | מפרק שורת shell לפקודות שהיא באמת מריצה. |
| `shell_strip.py` | מסיר משורת shell את מה שלא רץ: גופי heredoc והערות. |
