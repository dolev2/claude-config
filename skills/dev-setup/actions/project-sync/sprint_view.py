"""The board's "ספרינט נוכחי" view, kept on the current sprint.

The view filters on one milestone by name: GitHub has no `milestone:@current`. Each run
moves that filter to the current sprint, by the pipeline's one rule (sprint_rule.py: the
lowest-numbered open milestone with an open issue, PRs not counted, claude-config #164),
so the board follows the sprint the moment its last issue closes (claude-config #17).
Only the milestone term of that one view's filter changes; a view without one, and
every other view, are left alone. When no milestone has open issues the filter stays
where it is.
"""

import json
import re

import gh_api
from sprint_rule import current_sprint

SPRINT_VIEW = "ספרינט נוכחי"
MILESTONE_TERM = re.compile(r'milestone:(?:"[^"]*"|\S+)')

UPDATE_VIEW_FILTER = """
mutation($view:ID!, $filter:String!) {
  updateProjectV2View(input:{viewId:$view, filter:$filter}) { projectV2View { id } }
}
"""


def sprint_view_change(views: list[dict], sprint: str | None) -> tuple | None:
    """(view id, new filter) when the sprint view shows another milestone, else None."""
    view = next((v for v in views if v["name"] == SPRINT_VIEW), None)
    if not sprint or not view or not MILESTONE_TERM.search(view["filter"] or ""):
        return None
    wanted = MILESTONE_TERM.sub(
        lambda _: f'milestone:"{sprint}"', view["filter"], count=1
    )
    return (view["id"], wanted) if wanted != view["filter"] else None


def sync_sprint_view(repo: str, views: list[dict]) -> str | None:
    """Point the sprint view's milestone filter at the current sprint.

    Returns the new filter when it changed, else None.
    """
    pages = json.loads(
        gh_api.gh(
            "api",
            f"repos/{repo}/issues?state=open&per_page=100",
            "--paginate",
            "--slurp",
        )
    )
    issues = [issue for page in pages for issue in page]
    change = sprint_view_change(views, current_sprint(issues))
    if not change:
        return None
    gh_api.graphql(UPDATE_VIEW_FILTER, view=change[0], filter=change[1])
    return change[1]
