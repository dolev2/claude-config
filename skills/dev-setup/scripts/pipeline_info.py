"""Prints what the dev-* skills need to know about the repo they are running in.

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a logged-in
`gh`:

    python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
    python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py" --json

Nothing here is configured by hand. Every value is read from the repo itself, so the
same skills work in every repo that carries the pipeline:

- repo and default branch      - from `gh repo view`
- the human owner label        - the `owner:*` label that is not `owner:claude`
- the sync marker name         - the SYNC_MARKER variable, when the repo has the sync
                                 workflow
- the project number           - the PROJECT_NUMBER repository variable
- the current sprint           - the lowest-numbered open milestone with open issues
- where the issue forms live   - the repo's own .github/ISSUE_TEMPLATE, or else the
                                 account's public <owner>/.github repo, which GitHub
                                 serves to every repo without forms of its own
- repo-specific skills         - .claude/skills/* in the repo; when they cover the
                                 pipeline, they win over the generic dev-* skills
- the file guide               - a README.md with a "מדריך קבצים" / "File guide"
                                 heading; without one, missing_files names it
- the lint setup               - lint_check.py: settings missing or differing from the
                                 dev-setup templates, by the languages in the repo

`ready` is true when every pipeline label exists. When it is false, run dev-setup.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from lint_check import lint_gaps, tracked_files

REQUIRED_LABELS = [
    "owner:claude",
    "status:explore",
    "status:plan-questions",
    "status:waiting-approval",
    "status:ready-to-execute",
    "status:needs-repair",
    "status:in-review",
    "status:done",
    "status:backlog",
    "task",
    "bug",
    "process",
    "costs-money",
]
FORM_FILES = [
    ".github/ISSUE_TEMPLATE/task.yml",
    ".github/ISSUE_TEMPLATE/bug.yml",
]
PIPELINE_FILES = [
    ".github/workflows/sync-project.yml",
    ".github/workflows/open-questions-gate.yml",
]

FILE_GUIDE = "README.md"
FILE_GUIDE_HEADINGS = ("מדריך קבצים", "file guide")


def run(*args: str) -> tuple[int, str]:
    p = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return p.returncode, p.stdout.strip()


def repo_root() -> Path | None:
    code, out = run("git", "rev-parse", "--show-toplevel")
    return Path(out) if code == 0 and out else None


def sync_marker(root: Path | None, repo: str) -> str | None:
    """The marker name issue bodies carry, e.g. crm-sync. None when there is no sync.

    The shared sync action (dev-setup/actions/project-sync) reads it from the
    SYNC_MARKER variable only, so that is the one place to look. An empty variable is
    reported as missing rather than guessed: the action refuses to run without it.
    """
    workflow = root / ".github/workflows/sync-project.yml" if root else None
    if not workflow or not workflow.exists():
        return None
    code, out = run("gh", "variable", "get", "SYNC_MARKER", "--repo", repo)
    return out if code == 0 and out else None


def issue_forms(root: Path | None, repo: str) -> str | None:
    """Where the task and bug forms are read from: "repo", "<owner>/.github", or None.

    A repo with its own .github/ISSUE_TEMPLATE hides every default form, so the local
    copy wins whenever it exists. Otherwise GitHub serves the forms of the owner's
    public .github repo, from the same path inside it.
    """
    if root and all((root / f).exists() for f in FORM_FILES):
        return "repo"
    defaults = f"{repo.split('/')[0]}/.github"
    code, _ = run(
        "gh", "api", f"repos/{defaults}/contents/{FORM_FILES[0]}", "--jq", ".path"
    )
    return defaults if code == 0 else None


def has_file_guide(root: Path) -> bool:
    """True when README.md has a Markdown heading, at any level, naming the file guide.

    Only a heading counts: the words in a sentence ("see the file guide") are not a
    guide.
    """
    readme = root / FILE_GUIDE
    if not readme.exists():
        return False
    headings = re.findall(
        r"^#{1,6}\s+(.+)$",
        readme.read_text(encoding="utf-8", errors="replace"),
        re.MULTILINE,
    )
    return any(
        name in heading.lower() for heading in headings for name in FILE_GUIDE_HEADINGS
    )


def current_sprint(repo: str) -> str | None:
    code, out = run(
        "gh",
        "api",
        f"repos/{repo}/milestones?state=open&per_page=100",
        "--jq",
        "[.[] | select(.open_issues > 0)] | sort_by(.number) | .[0].title // empty",
    )
    return out or None if code == 0 else None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo", help="owner/name; defaults to the repo of the current directory"
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    view = ["gh", "repo", "view", "--json", "nameWithOwner,defaultBranchRef"]
    if args.repo:
        view.insert(3, args.repo)
    code, out = run(*view)
    if code != 0 or not out:
        sys.exit("Not inside a GitHub repo that gh can see; pass --repo owner/name.")
    meta = json.loads(out)
    repo = meta["nameWithOwner"]

    root = repo_root() if not args.repo else None
    _, labels_raw = run(
        "gh",
        "label",
        "list",
        "--repo",
        repo,
        "--limit",
        "300",
        "--json",
        "name",
        "--jq",
        ".[].name",
    )
    labels = set(labels_raw.splitlines())
    humans = sorted(
        name.removeprefix("owner:")
        for name in labels
        if name.startswith("owner:") and name != "owner:claude"
    )
    missing = [name for name in REQUIRED_LABELS if name not in labels]
    if not humans:
        missing.append("owner:<human>")
    code, project = run("gh", "variable", "get", "PROJECT_NUMBER", "--repo", repo)
    forms = issue_forms(root, repo)
    missing_files = (
        [f for f in PIPELINE_FILES if not (root / f).exists()] if root else []
    )
    if root and not has_file_guide(root):
        missing_files.append(f"{FILE_GUIDE} (file guide)")
    if not forms:
        missing_files.insert(
            0, f".github/ISSUE_TEMPLATE (repo or {repo.split('/')[0]}/.github)"
        )

    info = {
        "repo": repo,
        "default_branch": meta["defaultBranchRef"]["name"],
        "human": humans[0] if len(humans) == 1 else humans or None,
        "ready": not missing,
        "missing_labels": missing,
        "area_labels": sorted(name for name in labels if name.startswith("area:")),
        "sync_marker": sync_marker(root, repo),
        "project_number": int(project) if code == 0 and project.isdigit() else None,
        "current_sprint": current_sprint(repo),
        "root": str(root) if root else None,
        "issue_forms": forms,
        "missing_files": missing_files if root or not forms else None,
        "lint": lint_gaps(root, tracked_files(root)) if root else None,
        "claude_md": bool(root and (root / "CLAUDE.md").exists()),
        "repo_skills": sorted(
            p.parent.name for p in (root / ".claude/skills").glob("*/SKILL.md")
        )
        if root
        else [],
    }

    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return
    for key, value in info.items():
        print(f"{key:<16} {value}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
