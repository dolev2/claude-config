"""Reading and writing the Project (v2) board.

Why the project is read from the issue side
-------------------------------------------
`projectV2.items` returns an empty connection for this project even though the items
demonstrably exist (verified 2026-09-23: items added through the API were invisible
there for over ten minutes, on a freshly created project too, while a project populated
through the web UI reported its items correctly). `issue.projectItems` returns the same
items and their field values immediately, so that is the read path used here. Do not
"simplify" this back to iterating `projectV2.items` — it silently yields no state, which
the sync would read as "the board was never touched".
"""

import gh_api

PROJECT_QUERY = """
query($owner:String!, $number:Int!) {
  user(login:$owner) {
    projectV2(number:$number) {
      id
      views(first:30) { nodes { id name filter } }
      fields(first:30) {
        nodes {
          ... on ProjectV2SingleSelectField { id name options { id name } }
          ... on ProjectV2FieldCommon { id name }
        }
      }
    }
  }
}
"""

# The board items of one issue and their single-select values, in both queries below.
ITEM_FIELDS = """
        number
        projectItems(first:10) {
          nodes {
            id
            project { number }
            fieldValues(first:20) {
              nodes {
                ... on ProjectV2ItemFieldSingleSelectValue {
                  name
                  field { ... on ProjectV2FieldCommon { name } }
                }
              }
            }
          }
        }
"""

ISSUE_ITEMS = (
    """
query($owner:String!, $repo:String!, $after:String) {
  repository(owner:$owner, name:$repo) {
    issues(first:100, after:$after, states:[OPEN, CLOSED]) {
      pageInfo { hasNextPage endCursor }
      nodes {"""
    + ITEM_FIELDS
    + """      }
    }
  }
}
"""
)

ONE_ISSUE_ITEMS = (
    """
query($owner:String!, $repo:String!, $issue:Int!) {
  repository(owner:$owner, name:$repo) {
    issue(number:$issue) {"""
    + ITEM_FIELDS
    + """    }
  }
}
"""
)

# What GitHub answers when the issue is on the board already (claude-config #101): a
# parallel run added it, or the read at the start of the run did not show it yet.
ALREADY_ON_BOARD = "Content already exists in this project"

ADD_ITEM = """
mutation($project:ID!, $content:ID!) {
  addProjectV2ItemById(input:{projectId:$project, contentId:$content}) { item { id } }
}
"""

SET_SELECT = """
mutation($project:ID!, $item:ID!, $field:ID!, $option:String!) {
  updateProjectV2ItemFieldValue(input:{
    projectId:$project, itemId:$item, fieldId:$field,
    value:{singleSelectOptionId:$option}
  }) { projectV2Item { id } }
}
"""


def board_item(issue: dict, number: int) -> dict | None:
    """{"id": item id, "values": {field name: option}} of the issue on board number."""
    for it in issue["projectItems"]["nodes"]:
        if (it.get("project") or {}).get("number") != number:
            continue
        vals = {}
        for fv in it["fieldValues"]["nodes"]:
            if fv and fv.get("field"):
                vals[fv["field"]["name"]] = fv.get("name")
        return {"id": it["id"], "values": vals}
    return None


def load_items(repo: str, number: int) -> dict[int, dict]:
    """{issue number: {"id": item id, "values": {field name: option}}} on the board."""
    repo_owner, repo_name = repo.split("/", 1)
    by_issue = {}
    after = None
    while True:
        kw = {"owner": repo_owner, "repo": repo_name}
        if after:
            kw["after"] = after
        page = gh_api.graphql(ISSUE_ITEMS, **kw)["data"]["repository"]["issues"]
        for issue in page["nodes"]:
            item = board_item(issue, number)
            if item:
                by_issue[issue["number"]] = item
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    return by_issue


def load_project(owner: str, repo: str, number: int) -> tuple[str, dict, dict, list]:
    """(project id, fields by name, board item per issue number, views) of the board."""
    data = gh_api.graphql(PROJECT_QUERY, owner=owner, number=number)["data"]["user"][
        "projectV2"
    ]
    fields = {f["name"]: f for f in data["fields"]["nodes"] if f.get("name")}
    return data["id"], fields, load_items(repo, number), data["views"]["nodes"]


def add_item(project_id: str, repo: str, number: int, issue: dict) -> tuple[dict, bool]:
    """Put the issue on board number; return (its item, whether it was added now).

    An issue already on the board is not a failure (claude-config #101): its item is
    read back, with its values, and the sync goes on with it.
    """
    try:
        res = gh_api.graphql(ADD_ITEM, project=project_id, content=issue["id"])
    except RuntimeError as e:
        if ALREADY_ON_BOARD not in str(e):
            raise
        item = find_item(repo, number, issue["number"])
        if item is None:
            raise
        return item, False
    item_id = res["data"]["addProjectV2ItemById"]["item"]["id"]
    return {"id": item_id, "values": {}}, True


def find_item(repo: str, number: int, issue_number: int) -> dict | None:
    """The item of one issue on board number, with its values; None when not on it."""
    repo_owner, repo_name = repo.split("/", 1)
    data = gh_api.graphql(
        ONE_ISSUE_ITEMS, owner=repo_owner, repo=repo_name, issue=issue_number
    )
    return board_item(data["data"]["repository"]["issue"], number)


def set_field(project_id: str, item_id: str, field: dict, option_name: str) -> bool:
    """Set a single-select field on a board item; False when it lacks the option."""
    option = next(
        (o for o in field.get("options", []) if o["name"] == option_name), None
    )
    if option is None:
        return False
    gh_api.graphql(
        SET_SELECT,
        project=project_id,
        item=item_id,
        field=field["id"],
        option=option["id"],
    )
    return True
