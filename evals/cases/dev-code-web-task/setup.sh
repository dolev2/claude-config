# The repo with a spec part for a small web page (S-1.2), and the issue that builds it.
. "$(dirname "$0")/../scaffold.sh"
cat >> docs/specs/demo.md <<'SPEC'

## פרק 2 · דף הבית

### S-1.2 · דף בית עם חלון "אודות"
**מצב:** פתוח (#12)

דף HTML אחד, `index.html`, עם הברכה "Hello, stranger" וכפתור "אודות".
הכפתור פותח חלון קטן עם משפט על הריפו, וכפתור שסוגר אותו.

#### חוויית משתמש
1. החלון נפתח מעל הדף, והדף שמאחוריו לא לחיץ.
2. Escape סוגר אותו, והפוקוס חוזר לכפתור "אודות".

#### מה לא בחלק
עיצוב מעבר לברירת המחדל של הדפדפן.
SPEC
git add -A
git commit -q -m "אפיון: דף הבית"
git push -q origin main 2>/dev/null
seed_state
