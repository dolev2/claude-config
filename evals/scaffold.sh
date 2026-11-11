# Sourced by each case's setup.sh, which runs in the case's empty workspace.
# Builds what every case needs: a ~/.claude copy so the skills' $HOME/.claude/... paths
# work, the demo repo with a bare remote, and the fake gh's state (fake_gh_state.py).
set -eu
CASE_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_DIR="$(cd "$CASE_DIR/../.." && pwd)"
WORKSPACE="$PWD"
REMOTE="$HOME/git/acme/demo.git"

mkdir -p "$HOME/.claude"
cp -R "$PLUGIN_DIR/claude-home/." "$HOME/.claude/"

git config --global user.name "Eval"
git config --global user.email "eval@example.com"
git config --global init.defaultBranch main
git init -q --bare "$REMOTE"
git init -q .
git remote add origin "$REMOTE"
cp -R "$PLUGIN_DIR/evals/fixture/." .
git add -A
git commit -q -m "התחלה"
git push -q -u origin main 2>/dev/null

# Runs a case-specific step from the case's setup.sh, on a branch of its own.
on_branch() {
  git checkout -q -b "$1"
  shift
  "$@"
  git add -A
  git commit -q -m "עבודה על ה-branch"
  git push -q -u origin HEAD 2>/dev/null
  git checkout -q main
}

# The work of issue #12 (an empty name greets a stranger), with its spec part marked Done.
empty_name_change() {
  python3 - <<'PY'
from pathlib import Path
Path("greet.py").write_text('''"""Greetings."""


def greet(name: str) -> str:
    """A greeting for name; an empty name is a stranger."""
    return f"Hello, {name or 'stranger'}"
''')
test = Path("test_greet.py")
check = 'assert greet("") == "Hello, stranger"\nprint("ok")'
test.write_text(test.read_text().replace('print("ok")', check))
spec = Path("docs/specs/demo.md")
spec.write_text(spec.read_text().replace("פתוח (#12)", "Done (#12)"))
PY
}

seed_state() {
  mkdir -p gh-state
  python3 - "$CASE_DIR/state.json" "$REMOTE" gh-state/state.json <<'PY'
import json, sys
state = json.load(open(sys.argv[1], encoding="utf-8"))
state["git_remote"] = sys.argv[2]
json.dump(state, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
  : > gh-state/calls.jsonl
  echo "$WORKSPACE/gh-state" > "$HOME/.fake-gh-state"
  # The run mounts placeholders of config files into the workspace (.bashrc, .mcp.json
  # and the like); excluded, so a skill's `git status` sees only the repo's own files.
  cat >> .git/info/exclude <<'EX'
gh-state/
/.*
!/.github/
!/.gitignore
/bunfig.toml
/lefthook.y*ml
/*-wrapper.properties
/pyrightconfig.json
EX
  python3 "$(dirname "$(command -v gh)")/../fake_gh_state.py" gh-state
}
