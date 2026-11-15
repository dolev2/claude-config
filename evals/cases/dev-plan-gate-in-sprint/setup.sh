# The repo, with S-1.1 already built and Done on main (#11), so the code and the spec
# agree, and the issues: #12 asks for more than the Done part holds (#415).
. "$(dirname "$0")/../scaffold.sh"
empty_name_change
sed -i 's/Done (#12)/Done (#11)/' docs/specs/demo.md
git commit -qam "S-1.1 נבנה ב-#11"
git push -q origin main 2>/dev/null
seed_state
