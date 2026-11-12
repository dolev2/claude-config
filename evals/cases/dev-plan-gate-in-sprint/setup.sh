# The repo, with the spec part of #12 already Done on main, and the issues.
. "$(dirname "$0")/../scaffold.sh"
sed -i 's/פתוח (#12)/Done (#11)/' docs/specs/demo.md
git commit -qam "S-1.1 נבנה ב-#11"
git push -q origin main 2>/dev/null
seed_state
