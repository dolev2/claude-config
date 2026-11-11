"""The GitHub state behind fake_gh.py: issues, PRs and labels in one JSON file.

state.json holds `repo`, `default_branch`, `labels`, `milestones`, `issues` and `pulls`
(both keyed by number as a string), and optionally `git_remote`: the bare repo the
case's `origin` points at, used for PR head SHAs and for what a merge does to it.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_LABELS = [
    *(
        f"status:{name}"
        for name in (
            "explore",
            "plan-questions",
            "waiting-approval",
            "ready-to-execute",
            "needs-repair",
            "in-review",
            "done",
            "backlog",
        )
    ),
    *("task", "bug", "process", "costs-money", "area:core"),
]
CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b", re.I
)


class GhError(Exception):
    """A failed gh call: the message goes to stderr and the exit code is 1."""

    def __init__(
        self, message: str, *, unsupported: bool = False, output: str = ""
    ) -> None:
        super().__init__(message)
        self.message = message
        self.unsupported = unsupported
        self.output = output


def not_found() -> GhError:
    """What gh prints for a missing resource."""
    return GhError("gh: Not Found (HTTP 404)")


class State:
    """The JSON state of one case, and the files the graders read."""

    def __init__(self, folder: Path, data: dict) -> None:
        self.folder = folder
        self.data = data
        self.data.setdefault("issues", {})
        self.data.setdefault("pulls", {})
        self.data.setdefault("labels", list(DEFAULT_LABELS))
        self.data.setdefault("milestones", [])

    @classmethod
    def load(cls, folder: Path) -> State:
        """Read state.json from the folder."""
        path = folder / "state.json"
        return cls(folder, json.loads(path.read_text(encoding="utf-8")))

    @property
    def repo(self) -> str:
        return self.data.get("repo", "acme/demo")

    @property
    def default_branch(self) -> str:
        return self.data.get("default_branch", "main")

    # --- files -------------------------------------------------------------------

    def save(self) -> None:
        """Write state.json and the per-issue and per-PR files the graders read."""
        (self.folder / "state.json").write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for key, issue in self.data["issues"].items():
            base = self.folder / "issues" / key
            base.parent.mkdir(exist_ok=True)
            Path(f"{base}.labels").write_text(
                "".join(f"{label}\n" for label in sorted(issue.get("labels", []))),
                encoding="utf-8",
            )
            Path(f"{base}.body.md").write_text(issue.get("body", ""), encoding="utf-8")
            Path(f"{base}.state").write_text(issue.get("state", "open") + "\n")
            comments = "\n\n---\n\n".join(issue.get("comments", []))
            Path(f"{base}.comments.md").write_text(comments, encoding="utf-8")
        for key, pull in self.data["pulls"].items():
            base = self.folder / "pulls" / key
            base.parent.mkdir(exist_ok=True)
            status = "merged" if pull.get("merged") else pull.get("state", "open")
            Path(f"{base}.state").write_text(status + "\n")
            Path(f"{base}.body.md").write_text(pull.get("body", ""), encoding="utf-8")

    def log(self, entry: dict) -> None:
        """Append one call to calls.jsonl."""
        with (self.folder / "calls.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # --- git ---------------------------------------------------------------------

    def git(self, *args: str) -> str:
        """Run git; return stdout, or "" when it fails."""
        p = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
        return p.stdout.strip() if p.returncode == 0 else ""

    def current_branch(self) -> str:
        return self.git("rev-parse", "--abbrev-ref", "HEAD")

    def head_sha(self, pull: dict) -> str:
        """The PR's head SHA: from the bare remote when the case has one."""
        remote = self.data.get("git_remote")
        if remote:
            sha = self.git(
                f"--git-dir={remote}", "rev-parse", f"refs/heads/{pull['head']}"
            )
            if sha:
                return sha
        return pull.get("head_sha", "0" * 40)

    # --- issues ------------------------------------------------------------------

    def issue(self, number: int) -> dict:
        if str(number) in self.data["issues"]:
            return self.data["issues"][str(number)]
        raise not_found()

    def issue_numbers(self) -> list[int]:
        return sorted(int(n) for n in self.data["issues"])

    def issue_url(self, number: int) -> str:
        return f"https://github.com/{self.repo}/issues/{number}"

    def issue_matches(
        self, number: int, labels: list[str], milestone: str | None, wanted: str
    ) -> bool:
        """Whether an issue passes gh issue list's --label, --milestone, --state."""
        issue = self.issue(number)
        if wanted != "all" and issue.get("state", "open") != wanted:
            return False
        if milestone and issue.get("milestone") != milestone:
            return False
        return all(label in issue.get("labels", []) for label in labels)

    def closing_pulls(self, number: int) -> list[int]:
        """The PRs whose body closes this issue."""
        return [
            int(key)
            for key, pull in self.data["pulls"].items()
            if str(number) in CLOSING.findall(pull.get("body", ""))
        ]

    def issue_cli(self, number: int) -> dict:
        """An issue as `gh issue view --json` shows it."""
        issue = self.issue(number)
        milestone = issue.get("milestone")
        return {
            "number": number,
            "title": issue.get("title", ""),
            "body": issue.get("body", ""),
            "state": issue.get("state", "open").upper(),
            "labels": [{"name": label} for label in issue.get("labels", [])],
            "milestone": {"title": milestone} if milestone else None,
            "comments": [
                {"body": c, "author": {"login": "dolev2"}}
                for c in issue.get("comments", [])
            ],
            "url": self.issue_url(number),
            "closedByPullRequestsReferences": [
                {"number": p} for p in self.closing_pulls(number)
            ],
        }

    def blocking(self, number: int) -> list[int]:
        """The issues that list this one under blocked_by."""
        return [
            int(key)
            for key, issue in self.data["issues"].items()
            if number in issue.get("blocked_by", [])
        ]

    def thread(self, number: int) -> dict:
        """The issue or PR a comment goes to."""
        key = str(number)
        if key in self.data["pulls"]:
            return self.data["pulls"][key]
        return self.issue(number)

    def add_labels(self, number: int, labels: list[str]) -> None:
        issue = self.issue(number)
        for label in (x.strip() for x in labels):
            if label and label not in self.data["labels"]:
                raise GhError(f"'{label}' not found")
            if label and label not in issue.setdefault("labels", []):
                issue["labels"].append(label)

    def remove_labels(self, number: int, labels: list[str]) -> None:
        issue = self.issue(number)
        drop = {x.strip() for x in labels}
        issue["labels"] = [x for x in issue.get("labels", []) if x not in drop]

    def set_body(self, number: int, body: str) -> None:
        self.issue(number)["body"] = body

    def add_comment(self, number: int, body: str) -> None:
        self.thread(number).setdefault("comments", []).append(body)

    # --- pull requests -----------------------------------------------------------

    def pull(self, number: int) -> dict:
        if str(number) in self.data["pulls"]:
            return self.data["pulls"][str(number)]
        raise not_found()

    def pull_numbers(self) -> list[int]:
        return sorted(int(n) for n in self.data["pulls"])

    def pull_url(self, number: int) -> str:
        return f"https://github.com/{self.repo}/pull/{number}"

    def pull_status(self, pull: dict) -> str:
        """open, closed or merged."""
        return "merged" if pull.get("merged") else pull.get("state", "open")

    def pr_for_branch(self, branch: str) -> int:
        """The newest PR whose head is this branch."""
        found = [n for n in self.pull_numbers() if self.pull(n)["head"] == branch]
        if not found:
            raise GhError(f'no pull requests found for branch "{branch}"')
        return found[-1]

    def pull_matches(
        self, number: int, head: str | None, wanted: str, search: str | None
    ) -> bool:
        """Whether a PR passes gh pr list's --head, --state, --search."""
        pull = self.pull(number)
        if head and pull["head"] != head:
            return False
        if wanted != "all" and self.pull_status(pull) != wanted:
            if not (wanted == "closed" and pull.get("merged")):
                return False
        text = f"{pull.get('title', '')}\n{pull.get('body', '')}"
        return not search or search.strip("#") in text

    def checks(self, number: int) -> str:
        """The conclusion of the PR's checks: success unless the case says otherwise."""
        return self.pull(number).get("checks", "success")

    def pull_cli(self, number: int) -> dict:
        """A PR as `gh pr view --json` shows it."""
        pull = self.pull(number)
        mergeable = pull.get("mergeable", True)
        return {
            "number": number,
            "title": pull.get("title", ""),
            "body": pull.get("body", ""),
            "state": self.pull_status(pull).upper(),
            "headRefName": pull["head"],
            "headRefOid": self.head_sha(pull),
            "baseRefName": pull.get("base", self.default_branch),
            "mergeable": "MERGEABLE" if mergeable else "CONFLICTING",
            "mergeStateStatus": "CLEAN" if mergeable else "DIRTY",
            "url": self.pull_url(number),
            "closingIssuesReferences": [
                {"number": int(n)} for n in CLOSING.findall(pull.get("body", ""))
            ],
            "statusCheckRollup": [
                {
                    "name": "tests",
                    "status": "COMPLETED",
                    "conclusion": self.checks(number).upper(),
                }
            ],
        }

    def create_pull(self, *, title: str, body: str, head: str, base: str) -> int:
        """Open a PR; its number follows the highest issue or PR number."""
        if not head:
            raise GhError("fake gh: no head branch")
        taken = self.issue_numbers() + self.pull_numbers()
        number = max(taken, default=0) + 1
        self.data["pulls"][str(number)] = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
            "state": "open",
            "merged": False,
            "checks": self.data.get("new_pull_checks", "success"),
        }
        return number

    def edit_pull(self, number: int, title: str | None, body: str | None) -> None:
        pull = self.pull(number)
        if title is not None:
            pull["title"] = title
        if body is not None:
            pull["body"] = body

    def merge(self, number: int) -> None:
        """Merge: the PR closes, the issues it closes close, the remote's base moves."""
        pull = self.pull(number)
        if self.pull_status(pull) != "open":
            raise GhError(f"Pull request #{number} is not open")
        pull.update(state="closed", merged=True)
        for issue in CLOSING.findall(pull.get("body", "")):
            if issue in self.data["issues"]:
                self.data["issues"][issue]["state"] = "closed"
        remote = self.data.get("git_remote")
        if remote:
            sha = self.head_sha(pull)
            self.git(
                f"--git-dir={remote}", "update-ref", f"refs/heads/{pull['base']}", sha
            )
            self.git(
                f"--git-dir={remote}", "update-ref", "-d", f"refs/heads/{pull['head']}"
            )


if __name__ == "__main__":
    # The scaffold writes the first set of grader files before the run starts.
    State.load(Path(sys.argv[1])).save()
