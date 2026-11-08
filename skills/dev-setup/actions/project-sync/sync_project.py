"""One-way sync from issue labels to the repo's GitHub Project (v2) fields.

Why this exists
---------------
Claude reads and writes issue labels only (see reference/setup.md in the dev-setup
skill); the Project board is the human view. This script writes the labels onto the
board. Nothing on the board changes a label, with one exception for an issue opened
from the board (sync_rules.py).

Why there is also a poll
------------------------
`projects_v2_item` webhooks are only delivered for organization-owned projects. This
project belongs to a user account, so a card dragged on the board produces no event.
The scheduled run puts it back in the column of its label: sweep_all.py, run every 15
minutes for every repo at once from the public dolev2/.github (claude-config #46). The
same run catches up on an issue event whose run failed.

Where each part lives
---------------------
This file is the entry point: settings, the loop over issues, and what is printed.
The rules (what is written where) are in sync_rules.py, the board reads and writes in
board.py (and why the board is read from the issue side), the sprint view in
sprint_view.py, the current-sprint rule in sprint_rule.py (a copy of the scripts' one),
and gh / GraphQL in gh_api.py. They
are flat modules next to this file, so every copy of it must ship the whole folder:
action.yml runs it in place, and dolev2/.github's sync-boards.yml downloads every .py
here (claude-config #57). A failure to move the sprint view is printed and the issue
sync goes on.

Quiet mode
----------
With SYNC_QUIET set, nothing that names an issue, a status or a sprint is printed; the
run ends with two lines, "updated issues: N" and "active without a sprint: N" (an open
issue in the pipeline, past backlog and short of done, with no milestone; claude-config
#55). sweep_all.py runs this script that way from the public dolev2/.github, whose logs
anyone can read (claude-config #46). Without SYNC_QUIET each such issue is named
instead.

One copy for every repo
-----------------------
This folder lives in dolev2/claude-config, skills/dev-setup/actions/project-sync, and
every repo's sync-project.yml calls it (claude-config #3; the per-repo copies had
drifted). So nothing repo-specific is written here: the Area options are read from the
board, and the one Status option whose name differs between boards is resolved against
the board too (resolve_options). SYNC_MARKER, which repos installed before #111 still
pass, is ignored.
"""

import json
import os
import sys
from dataclasses import dataclass

import board
import gh_api
import sprint_view
import sync_rules


@dataclass(frozen=True)
class Settings:
    """What one run needs from its environment."""

    repo: str
    project_owner: str
    project_number: int
    quiet: bool
    only_issue: str


@dataclass
class Board:
    """The board as loaded at the start of the run."""

    project_id: str
    fields: dict
    items: dict
    views: list


def check_environment() -> None:
    """Fail loudly on a missing token or project number.

    `gh secret set` cannot tell an empty paste from a real one, so a secret that was
    never actually pasted still reports success and then arrives here as an empty
    string. Without this check the first symptom is a gh usage message buried in a
    traceback, which reads like a bug in this script rather than a missing secret.
    """
    if not os.environ.get("GH_TOKEN", "").strip():
        raise SystemExit(
            "GH_TOKEN is empty. "
            "The PROJECT_TOKEN secret is unset or was stored empty.\n"
            "Set it again with:  $t = Read-Host 'Paste token'; "
            "gh secret set PROJECT_TOKEN --body $t; Remove-Variable t"
        )
    if not os.environ.get("PROJECT_NUMBER", "").strip():
        raise SystemExit(
            "PROJECT_NUMBER is empty. Set the repository variable:  "
            "gh variable set PROJECT_NUMBER --body 1"
        )


def load_settings() -> Settings:
    """The run's settings, read from the environment."""
    repo = os.environ["GITHUB_REPOSITORY"]
    return Settings(
        repo=repo,
        project_owner=os.environ.get("PROJECT_OWNER") or repo.split("/", 1)[0],
        project_number=int(os.environ.get("PROJECT_NUMBER", "0").strip() or 0),
        quiet=bool(os.environ.get("SYNC_QUIET", "").strip()),
        only_issue=os.environ.get("ISSUE_NUMBER", "").strip(),
    )


def report(settings: Settings, line: str) -> None:
    """Print a line that names an issue, a status or a sprint; silent in quiet mode."""
    if not settings.quiet:
        print(line)


def as_issue(item: dict) -> dict:
    """A REST issue in the shape the sync reads (the old `gh issue list --json`)."""
    reason = item.get("state_reason")
    return {
        "number": item["number"],
        "labels": [{"name": label["name"]} for label in item["labels"]],
        "id": item["node_id"],
        "state": item["state"].upper(),
        "stateReason": reason.upper() if reason else None,
        "milestone": item.get("milestone"),
    }


def load_issues(settings: Settings) -> list[dict]:
    """Every issue of the repo, open and closed, or ISSUE_NUMBER alone.

    Read through REST over every page: `gh issue list --limit 500` stopped at 500, and
    even ISSUE_NUMBER was looked for inside that list (claude-config #164).
    Pull requests are left out.
    """
    if settings.only_issue:
        items = [
            json.loads(
                gh_api.gh("api", f"repos/{settings.repo}/issues/{settings.only_issue}")
            )
        ]
    else:
        pages = json.loads(
            gh_api.gh(
                "api",
                f"repos/{settings.repo}/issues?state=all&per_page=100",
                "--paginate",
                "--slurp",
            )
        )
        items = [item for page in pages for item in page]
    return [as_issue(item) for item in items if "pull_request" not in item]


def apply_to_labels(
    settings: Settings, num: int, labels: list[str], state: dict[str, str]
) -> None:
    """Rewrite the issue's status/area labels to state, taken from its card."""
    args = sync_rules.label_edit_args(labels, state)
    if args:
        gh_api.gh("issue", "edit", str(num), "--repo", settings.repo, *args)
        report(settings, f"#{num} labels <- project: {state}")


def apply_to_board(
    settings: Settings, project: Board, num: int, item: dict, changes: dict[str, str]
) -> None:
    """Set the board item's Status/Area fields to the labels' values in changes."""
    for key, field_name, options in sync_rules.DIMENSIONS:
        suffix = changes.get(key)
        if not suffix:
            continue
        field = project.fields.get(field_name)
        if field is None:
            report(settings, f"  ! the project has no field {field_name!r} - skipped")
            continue
        option_name = options[suffix]
        if not board.set_field(project.project_id, item["id"], field, option_name):
            report(
                settings,
                f"  ! field {field['name']!r} has no option {option_name!r} - skipped",
            )
    report(settings, f"#{num} project <- labels: {changes}")


def clear_status(settings: Settings, project: Board, num: int, item: dict) -> bool:
    """Empty the Status of a decision issue's card; True when it did."""
    field = project.fields.get("Status")
    if field is None:
        report(settings, "  ! the project has no field 'Status' - skipped")
        return False
    board.clear_field(project.project_id, item["id"], field)
    report(settings, f"#{num} decision: board status cleared")
    return True


def sync_issue(settings: Settings, project: Board, issue: dict) -> bool:
    """Sync one issue that takes part; True when anything was written."""
    num = issue["number"]
    labels = [label["name"] for label in issue["labels"]]
    item = project.items.get(num)
    is_new = False
    if item is None:
        item, is_new = board.add_item(
            project.project_id, settings.repo, settings.project_number, issue
        )
        if is_new:
            report(settings, f"#{num} added to the project")

    on_board = sync_rules.project_state(item["values"])
    state = sync_rules.labels_state(labels)
    adopted = sync_rules.labels_from_board(labels, on_board)
    if adopted:
        apply_to_labels(settings, num, labels, adopted)
        state = adopted
    changes = sync_rules.board_changes(state, on_board)
    if changes:
        apply_to_board(settings, project, num, item, changes)
    cleared = sync_rules.clears_status(labels, item["values"]) and clear_status(
        settings, project, num, item
    )
    return is_new or bool(adopted) or bool(changes) or cleared


def close_out(settings: Settings, issue: dict) -> bool:
    """Move a closed-as-completed issue's labels to status:done; True when it did.

    The issue's labels are updated in place, so the sync that follows sees status:done
    and moves the card to Done.
    """
    labels = [label["name"] for label in issue["labels"]]
    if not sync_rules.needs_done_label(
        labels, issue["state"], issue.get("stateReason")
    ):
        return False
    new_labels = sync_rules.done_labels(labels)
    args = sync_rules.label_edit_args(labels, sync_rules.labels_state(new_labels))
    gh_api.gh("issue", "edit", str(issue["number"]), "--repo", settings.repo, *args)
    issue["labels"] = [{"name": name} for name in new_labels]
    report(settings, f"#{issue['number']} closed as completed -> status:done")
    return True


def takes_part(settings: Settings, project: Board, issue: dict) -> bool:
    """Whether the loop syncs this issue; reports one with doubled labels."""
    labels = [label["name"] for label in issue["labels"]]
    num = issue["number"]
    if not sync_rules.should_sync(labels, issue["state"], num in project.items):
        return False
    doubled = sync_rules.doubled_dimensions(labels)
    if doubled:
        report(
            settings, f"! #{num} has more than one {'/'.join(doubled)} label - skipped"
        )
        return False
    return True


def main() -> None:
    """Write the labels of every pipeline issue (or ISSUE_NUMBER alone) to the board."""
    check_environment()
    settings = load_settings()
    project = Board(
        *board.load_project(
            settings.project_owner, settings.repo, settings.project_number
        )
    )
    sync_rules.resolve_options(project.fields)
    try:
        moved_to = sprint_view.sync_sprint_view(settings.repo, project.views)
        if moved_to:
            report(settings, f"sprint view -> {moved_to}")
    except RuntimeError as e:
        report(settings, f"! sprint view not updated: {e}")

    updated = without_sprint = 0
    for issue in load_issues(settings):
        labels = [label["name"] for label in issue["labels"]]
        if sync_rules.is_active_without_sprint(issue, labels):
            without_sprint += 1
            report(settings, f"! #{issue['number']} is active but has no sprint")
        closed_out = close_out(settings, issue)
        if takes_part(settings, project, issue):
            updated += sync_issue(settings, project, issue) or closed_out
    if settings.quiet:
        print(f"updated issues: {updated}")
        print(f"active without a sprint: {without_sprint}")


if __name__ == "__main__":
    sys.exit(main())
