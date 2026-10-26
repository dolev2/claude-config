"""Reports what a repo is missing of the lint setup that dev-setup installs.

Run on its own from anywhere inside a repo (stdlib only), or through pipeline_info.py, which
shows the same list under `lint`:

    python "$HOME/.claude/skills/dev-setup/scripts/lint_check.py"

Each repo keeps its own copy of the lint settings, copied from ../templates (decided in
claude-config#21: ruff cannot read settings from a URL, and a shared copy would turn every
repo red at once). A copy is identical to its template above the "--- local ---" line, and
that is what is compared here; below the line each repo writes what is its own.

What is checked, by the files git tracks:
- a .py file        -> ruff.toml at the root, and `ruff check` in the tests workflow
- a .jsx file       -> eslint.config.js next to the nearest package.json, and `run lint`
"""

import subprocess
import sys
from pathlib import Path, PurePosixPath

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
# The whole line, so a comment that mentions the marker does not count as one.
LOCAL_MARKERS = ("# --- local ---", "// --- local ---")
WORKFLOW = ".github/workflows/tests.yml"


def shared_part(text: str) -> str | None:
    """The text above the local marker line, with LF line endings; None without a marker."""
    lines = text.replace("\r\n", "\n").split("\n")
    for index, line in enumerate(lines):
        if line.strip() in LOCAL_MARKERS:
            return "\n".join(lines[:index])
    return None


def config_gap(root: Path, path: str, template: str) -> str | None:
    """A gap line when the copy is absent ("missing") or strays from the template ("differs")."""
    copy = root / path
    if not copy.exists():
        return f"missing {path}"
    expected = shared_part((TEMPLATES / template).read_text(encoding="utf-8"))
    actual = shared_part(copy.read_text(encoding="utf-8", errors="replace"))
    return None if actual == expected else f"differs {path}"


def react_folders(files: list[str]) -> list[str]:
    """The folders, relative to the root, of the package.json nearest to each .jsx file."""
    packages = {str(PurePosixPath(f).parent) for f in files if PurePosixPath(f).name == "package.json"}
    folders = set()
    for f in files:
        if not f.endswith(".jsx"):
            continue
        folder = PurePosixPath(f).parent
        while str(folder) not in packages and str(folder) != ".":
            folder = folder.parent
        folders.add(str(folder))
    return sorted(folders)


def workflow_gaps(root: Path, has_python: bool, has_react: bool) -> list[str]:
    """What the tests workflow lacks: the file itself, or a lint step for a language in use."""
    workflow = root / WORKFLOW
    if not workflow.exists():
        return [f"missing {WORKFLOW}"]
    text = workflow.read_text(encoding="utf-8", errors="replace")
    gaps = []
    if has_python and "ruff check" not in text:
        gaps.append(f"no ruff step in {WORKFLOW}")
    if has_react and "run lint" not in text:
        gaps.append(f"no lint step in {WORKFLOW}")
    return gaps


def lint_gaps(root: Path, files: list[str]) -> list[str]:
    """Every gap in the repo's lint setup, given the files git tracks; empty when complete."""
    has_python = any(f.endswith(".py") for f in files)
    folders = react_folders(files)
    gaps = [config_gap(root, "ruff.toml", "ruff.toml")] if has_python else []
    for folder in folders:
        path = "eslint.config.js" if folder == "." else f"{folder}/eslint.config.js"
        gaps.append(config_gap(root, path, "eslint.config.js"))
    if has_python or folders:
        gaps += workflow_gaps(root, has_python, bool(folders))
    return [gap for gap in gaps if gap]


def tracked_files(root: Path) -> list[str]:
    """The paths git tracks under root, with forward slashes."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files"], capture_output=True, text=True, encoding="utf-8", check=False
    )
    return result.stdout.splitlines() if result.returncode == 0 else []


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False)
    if top.returncode != 0:
        sys.exit("Not inside a git repo.")
    repo = Path(top.stdout.strip())
    for line in lint_gaps(repo, tracked_files(repo)) or ["lint setup complete"]:
        print(line)
