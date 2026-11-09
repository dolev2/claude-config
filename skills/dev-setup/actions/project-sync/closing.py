"""What the sync does with a closed issue before the rest of the loop sees it.

Closed as completed, it gets status:done, and its card moves to Done like any label
change (claude-config #97). Closed and not done (not planned, a duplicate), its card
leaves the board for the board's archive: should_sync no longer writes it, so the card
would sit in its last column for good (claude-config #219). An issue closed that way
and not on the board is not added.

Each function returns the line to report, or None when it did nothing; the caller
prints it, so quiet mode stays in sync_project.py.
"""

import board
import gh_api
import sync_rules


def close_out(repo: str, issue: dict) -> str | None:
    """Move a closed-as-completed issue's labels to status:done.

    The issue's labels are updated in place, so the sync that follows sees status:done
    and moves the card to Done.
    """
    labels = [label["name"] for label in issue["labels"]]
    if not sync_rules.needs_done_label(
        labels, issue["state"], issue.get("stateReason")
    ):
        return None
    new_labels = sync_rules.done_labels(labels)
    args = sync_rules.label_edit_args(labels, sync_rules.labels_state(new_labels))
    gh_api.gh("issue", "edit", str(issue["number"]), "--repo", repo, *args)
    issue["labels"] = [{"name": name} for name in new_labels]
    return f"#{issue['number']} closed as completed -> status:done"


def archive_out(project_id: str, items: dict[int, dict], issue: dict) -> str | None:
    """Archive the card of an issue closed and not done, and drop it from items."""
    labels = [label["name"] for label in issue["labels"]]
    num = issue["number"]
    if not sync_rules.should_archive(
        labels, issue["state"], issue.get("stateReason"), num in items
    ):
        return None
    board.archive_item(project_id, items.pop(num)["id"])
    return f"#{num} closed, not done -> archived from the board"
