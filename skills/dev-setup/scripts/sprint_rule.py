"""The pipeline's one rule for the current sprint, shared by every script that needs it.

The current sprint is the open milestone with the lowest number that still has an open
issue (../reference/pipeline.md, "ספרינטים"). A pull request does not count: GitHub's
`milestone.open_issues` counts open PRs too, so a sprint whose last issue closed while a
PR stayed open would still read as current there (claude-config #164).

rank_issues.py, pipeline_info.py and the board's sprint view all call this function.
The board sync is downloaded as a flat folder of its own, so it carries a copy at
actions/project-sync/sprint_rule.py; test_sprint_rule.py keeps the two identical.
"""


def current_sprint(issues: list[dict]) -> str | None:
    """Title of the current sprint among `issues`, or None when no milestone qualifies.

    `issues` are open issues, as REST items or as the GraphQL-shaped nodes of
    gh_rest.py: each with a `milestone` of `number`, `title` and `state` (in any case),
    or None. Items that are pull requests, or that are not open, are skipped.
    """
    milestones = {
        m["number"]: m["title"]
        for item in issues
        if "pull_request" not in item
        and str(item.get("state", "open")).lower() == "open"
        and (m := item.get("milestone"))
        and str(m["state"]).lower() == "open"
    }
    return milestones[min(milestones)] if milestones else None
