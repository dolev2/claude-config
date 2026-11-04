"""Two-way sync between issue labels and the repo's GitHub Project (v2) fields.

Why this exists
---------------
Claude reads and writes issue labels only (see reference/setup.md in the dev-setup
skill); the Project board is the human view. This script keeps the two in agreement.

Why it is a poll and not a webhook
----------------------------------
`projects_v2_item` webhooks are only delivered for organization-owned projects. This
project belongs to a user account, so a field edit made by dragging a card on the board
produces no event. The scheduled run is what notices it: sweep_all.py, run every 15
minutes for every repo at once from the public dolev2/.github (claude-config #46).

Where each part lives
---------------------
This file is the entry point: settings, the loop over issues, and what is printed.
The conflict rule (which side wins) is in sync_rules.py, the hidden marker in
marker.py, the board reads and writes in board.py (and why the board is read from the
issue side), the sprint view in sprint_view.py, and gh / GraphQL in gh_api.py. They
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
drifted). So nothing repo-specific is written here: the marker name comes from
SYNC_MARKER, the Area options are read from the board, and the one Status option whose
name differs between boards is resolved against the board too (resolve_options).
"""

import json
import os
import sys
import tempfile
from dataclasses import dataclass

import board
import gh_api
import marker
import sprint_view
import sync_rules


@dataclass(frozen=True)
class Settings:
    """What one run needs from its environment."""

    repo: str
    project_owner: str
    project_number: int
    marker_name: str
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
    """Fail loudly on a missing token, project number or marker name.

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
    # There is no default marker name on purpose - a wrong default makes every issue
    # look unsynced, and the stale board then wins over the labels.
    if not os.environ.get("SYNC_MARKER", "").strip():
        raise SystemExit(
            "SYNC_MARKER is empty. "
            "Set it to the marker name the issue bodies already carry\n"
            "(e.g. crm-sync):  gh variable set SYNC_MARKER --body <name>"
        )


def load_settings() -> Settings:
    """The run's settings, read from the environment."""
    repo = os.environ["GITHUB_REPOSITORY"]
    return Settings(
        repo=repo,
        project_owner=os.environ.get("PROJECT_OWNER") or repo.split("/", 1)[0],
        project_number=int(os.environ.get("PROJECT_NUMBER", "0").strip() or 0),
        marker_name=os.environ.get("SYNC_MARKER", "").strip(),
        quiet=bool(os.environ.get("SYNC_QUIET", "").strip()),
        only_issue=os.environ.get("ISSUE_NUMBER", "").strip(),
    )


def report(settings: Settings, line: str) -> None:
    """Print a line that names an issue, a status or a sprint; silent in quiet mode."""
    if not settings.quiet:
        print(line)


def load_issues(settings: Settings) -> list[dict]:
    """Every issue of the repo, open and closed, or ISSUE_NUMBER alone."""
    issues = json.loads(
        gh_api.gh(
            "issue",
            "list",
            "--repo",
            settings.repo,
            "--state",
            "all",
            "--limit",
            "500",
            "--json",
            "number,body,labels,id,state,stateReason,milestone",
        )
    )
    if settings.only_issue:
        issues = [i for i in issues if i["number"] == int(settings.only_issue)]
    return issues


def edit_body(repo: str, number: int, new_body: str) -> None:
    """Replace the issue's body, through a file so line endings survive."""
    f = tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8", newline="\n"
    )
    f.write(new_body)
    f.close()
    try:
        gh_api.gh("issue", "edit", str(number), "--repo", repo, "--body-file", f.name)
    finally:
        os.unlink(f.name)


def apply_to_labels(
    settings: Settings, num: int, labels: list[str], winner: dict[str, str]
) -> None:
    """Rewrite the issue's status/area labels to the board's state."""
    args = sync_rules.label_edit_args(labels, winner)
    if args:
        gh_api.gh("issue", "edit", str(num), "--repo", settings.repo, *args)
        report(settings, f"#{num} labels <- project: {winner}")


def apply_to_board(
    settings: Settings, project: Board, num: int, item: dict, winner: dict[str, str]
) -> None:
    """Set the board item's Status/Area fields to the labels' state."""
    for key, field_name, options in sync_rules.DIMENSIONS:
        suffix = winner.get(key)
        if not suffix or item["values"].get(field_name) == options[suffix]:
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
    report(settings, f"#{num} project <- labels: {winner}")


def sync_issue(settings: Settings, project: Board, issue: dict) -> bool:
    """Sync one issue that takes part; True when anything was written."""
    num = issue["number"]
    labels = [label["name"] for label in issue["labels"]]
    item = project.items.get(num)
    is_new = item is None
    if is_new:
        item = board.add_item(project.project_id, issue["id"])
        report(settings, f"#{num} added to the project")

    winner, source = sync_rules.choose_winner(
        marker.read_marker(issue["body"], settings.marker_name),
        sync_rules.labels_state(labels),
        sync_rules.project_state(item["values"]),
    )
    if source is None:
        return is_new  # already in agreement
    if source == "project":
        apply_to_labels(settings, num, labels, winner)
    else:
        apply_to_board(settings, project, num, item, winner)

    new_body = marker.write_marker(issue["body"], winner, settings.marker_name)
    if new_body != (issue["body"] or ""):
        edit_body(settings.repo, num, new_body)
    return True


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
    """Sync every pipeline issue (or ISSUE_NUMBER alone) between labels and board."""
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
