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

ISSUE_ITEMS = """
query($owner:String!, $repo:String!, $after:String) {
  repository(owner:$owner, name:$repo) {
    issues(first:100, after:$after, states:[OPEN, CLOSED]) {
      pageInfo { hasNextPage endCursor }
      nodes {
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
      }
    }
  }
}
"""

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
            for it in issue["projectItems"]["nodes"]:
                if (it.get("project") or {}).get("number") != number:
                    continue
                vals = {}
                for fv in it["fieldValues"]["nodes"]:
                    if fv and fv.get("field"):
                        vals[fv["field"]["name"]] = fv.get("name")
                by_issue[issue["number"]] = {"id": it["id"], "values": vals}
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


def add_item(project_id: str, content_id: str) -> dict:
    """Add an issue to the board; return its new, empty item."""
    res = gh_api.graphql(ADD_ITEM, project=project_id, content=content_id)
    return {"id": res["data"]["addProjectV2ItemById"]["item"]["id"], "values": {}}


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
