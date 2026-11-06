"""Prints what the dev-* skills need to know about the repo they are running in.

Run from anywhere inside the repo, with any Python 3.11+ (stdlib only) and a logged-in
`gh`:

    python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py"
    python "$HOME/.claude/skills/dev-setup/scripts/pipeline_info.py" --json

Nothing here is configured by hand. Every value is read from the repo itself, so the
same skills work in every repo that carries the pipeline:

- repo and default branch      - the `origin` remote, then REST (GraphQL is blocked
                                 in cloud sessions, claude-config #138)
- the project number           - the PROJECT_NUMBER repository variable; None when
                                 it is missing or unreadable (blocked in the cloud)
- the current sprint           - the lowest-numbered open milestone with open issues
- where the issue forms live   - the repo's own .github/ISSUE_TEMPLATE, or else the
                                 account's public <owner>/.github repo, which GitHub
                                 serves to every repo without forms of its own
- repo-specific skills         - .claude/skills/* in the repo; when they cover the
                                 pipeline, they win over the generic dev-* skills
- the file guide               - a README.md with a "מדריך קבצים" / "File guide"
                                 heading; without one, missing_files names it
- the lint setup               - lint_check.py: settings missing or differing from the
                                 dev-setup templates, by the languages in the repo,
                                 and the file guide check every repo copies (#89)
- the Netlify deploy rule      - a netlify.toml without build.ignore deploys, and pays
                                 credits, on every merge (claude-config#50)

`ready` is true when every pipeline label exists. When it is false, run dev-setup.
"""

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

from gh_rest import current_repo
from gh_rest import run as gh_run
from lint_check import all_gaps, tracked_files

REQUIRED_LABELS = [
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

NETLIFY_CONFIG = "netlify.toml"
FILE_GUIDE = "README.md"
FORMS_UNKNOWN = "unknown (no access from this session)"
FILE_GUIDE_HEADINGS = ("מדריך קבצים", "file guide")


def run(*args: str) -> tuple[int, str]:
    """Run a command; return its exit code and stdout (gh_rest.run without stderr)."""
    code, out, _ = gh_run(*args)
    return code, out


def repo_root() -> Path | None:
    code, out = run("git", "rev-parse", "--show-toplevel")
    return Path(out) if code == 0 and out else None


def issue_forms(root: Path | None, repo: str) -> str | None:
    """Where the task and bug forms are read from: "repo", "<owner>/.github", or None.

    A repo with its own .github/ISSUE_TEMPLATE hides every default form, so the local
    copy wins whenever it exists. Otherwise GitHub serves the forms of the owner's
    public .github repo, from the same path inside it.

    Only a 404 means the forms are missing. Any other failure (a cloud session reaches
    only the repos attached to it, HTTP 403) says FORMS_UNKNOWN, which is not reported
    as missing.
    """
    if root and all((root / f).exists() for f in FORM_FILES):
        return "repo"
    defaults = f"{repo.split('/')[0]}/.github"
    code, _, err = gh_run(
        "gh", "api", f"repos/{defaults}/contents/{FORM_FILES[0]}", "--jq", ".path"
    )
    if code == 0:
        return defaults
    return None if "HTTP 404" in err else FORMS_UNKNOWN


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


def netlify_gaps(root: Path) -> list[str]:
    """What the repo's netlify.toml lacks of the deploy-skip rule; empty without one.

    Without build.ignore Netlify deploys on every merge, workflows and docs included,
    and each deploy costs credits (claude-config#50). The rule is in
    templates/netlify.toml.
    """
    config = root / NETLIFY_CONFIG
    if not config.exists():
        return []
    try:
        settings = tomllib.loads(config.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        return [f"{NETLIFY_CONFIG} does not parse as TOML"]
    if not settings.get("build", {}).get("ignore"):
        return [f"no build.ignore in {NETLIFY_CONFIG}"]
    return []


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

    repo = args.repo or current_repo()
    code, default_branch, err = gh_run(
        "gh", "api", f"repos/{repo}", "--jq", ".default_branch"
    )
    if code != 0 or not default_branch:
        sys.exit(f"gh api repos/{repo} failed:\n{err}")

    root = repo_root() if not args.repo else None
    _, labels_raw = run(
        "gh",
        "api",
        "--paginate",
        f"repos/{repo}/labels?per_page=100",
        "--jq",
        ".[].name",
    )
    labels = set(labels_raw.splitlines())
    missing = [name for name in REQUIRED_LABELS if name not in labels]
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
        "default_branch": default_branch,
        "ready": not missing,
        "missing_labels": missing,
        "area_labels": sorted(name for name in labels if name.startswith("area:")),
        "project_number": int(project) if code == 0 and project.isdigit() else None,
        "current_sprint": current_sprint(repo),
        "root": str(root) if root else None,
        "issue_forms": forms,
        "missing_files": missing_files if root or not forms else None,
        "lint": all_gaps(root, tracked_files(root)) if root else None,
        "netlify": netlify_gaps(root) if root else None,
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
