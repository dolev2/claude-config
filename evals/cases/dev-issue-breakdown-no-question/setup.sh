# The repo, with S-1.1 built and Done on main (#12, closed), and a merged chapter 2 with
# two open parts and no issue yet: S-2.2 depends on S-2.1. The one milestone, "Sprint 1",
# is not named for that topic (#485).
. "$(dirname "$0")/../scaffold.sh"
empty_name_change
cat >> docs/specs/demo.md <<'MD'

## פרק 2 · פרידות

### S-2.1 · פרידה לפי שם

המשתמש נותן שם, ומקבל פרידה שמתחילה ב-"Goodbye".

#### חוויית משתמש
אין ממשק.

#### מה לא בחלק
תרגום.

### S-2.2 · פרידה ריקה

תלוי ב-S-2.1.

כשהשם ריק, הפרידה היא "Goodbye, stranger".

#### חוויית משתמש
אין ממשק.

#### מה לא בחלק
שם של רווחים.
MD
git commit -qam "אפיון: פרידות"
git push -q origin main 2>/dev/null
seed_state
