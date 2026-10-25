"""Two-way sync between issue labels and the repo's GitHub Project (v2) fields.

Why this exists
---------------
Claude reads and writes issue labels only (see reference/pipeline.md in the dev-setup skill); the
Project board is the human view. This script keeps the two in agreement.

Why it is a poll and not a webhook
----------------------------------
`projects_v2_item` webhooks are only delivered for organization-owned projects. This
project belongs to a user account, so a field edit made by dragging a card on the board
produces no event. The scheduled run is what notices it.

Why the project is read from the issue side
-------------------------------------------
`projectV2.items` returns an empty connection for this project even though the items
demonstrably exist (verified 2026-09-23: items added through the API were invisible there
for over ten minutes, on a freshly created project too, while a project populated through
the web UI reported its items correctly). `issue.projectItems` returns the same items and
their field values immediately, so that is the read path used here. Do not "simplify" this
back to iterating `projectV2.items` — it silently yields no state, which this script would
read as "the board was never touched".

Conflict resolution
-------------------
Each issue body carries a hidden marker recording the state at the end of the last sync:

    <!-- <SYNC_MARKER>: owner=claude status=explore area=backend -->

On each run the three states (marker / labels / project) are compared. Whichever of
labels or project differs from the marker is the side that changed and therefore wins;
if both changed, the project wins, because that edit was a deliberate human drag while a
label may have been set by an earlier automated step. A board item with no Owner/Status/
Area at all always takes the labels, even when they match the marker. The winner is then
written to the other side and the marker is rewritten.

The sprint view
---------------
The board's "ספרינט נוכחי" view filters on one milestone by name: GitHub has no
`milestone:@current`. Each run moves that filter to the current sprint, the pipeline's rule
(the lowest-numbered open milestone with open issues), so the board follows the sprint the
moment its last issue closes (claude-config #17). Only the milestone term of that one view's
filter changes; a view without one, and every other view, are left alone. When no milestone
has open issues the filter stays where it is. A failure here is printed and the issue sync
goes on.

One copy for every repo
-----------------------
This file lives in dolev2/claude-config, dev-setup/actions/project-sync, and every repo's
sync-project.yml calls it (claude-config #3; the per-repo copies had drifted). So nothing
repo-specific is written here: the marker name comes from SYNC_MARKER, the Area options are
read from the board, and the one Status option whose name differs between boards is
resolved against the board too (resolve_options).
"""

import json
import os
import re
import subprocess
import sys
import tempfile

REPO = os.environ["GITHUB_REPOSITORY"]
PROJECT_OWNER = os.environ.get("PROJECT_OWNER") or REPO.split("/", 1)[0]

# The marker name differs per repo (crm-sync, wayout-sync, ...). Never rename it once
# issues carry it: a body whose marker is not found looks like it was never synced. There is
# no default on purpose - a wrong default makes every issue look unsynced, and the stale
# board then wins over the labels (check_environment stops the run instead).
SYNC_MARKER = os.environ.get("SYNC_MARKER", "").strip()
MARKER_RE = re.compile(r"<!--\s*" + re.escape(SYNC_MARKER) + r":(.*?)-->", re.S)

# label suffix  ->  the option name as it appears in the Project's single-select field
OWNER_OPTIONS = {"claude": "Claude", "dolev": "Dolev"}
STATUS_OPTIONS = {
    "explore": "Explore (Claude)",
    # No owner in the name: an open question can sit with either side, and the Owner
    # column already says whose turn it is.
    "plan-questions": "Plan questions",  # or a name from STATUS_ALIASES, per board
    "waiting-approval": "Waiting for Dolev approval",
    "ready-to-execute": "Ready to execute (Claude)",
    "needs-repair": "Needs repair (Claude)",
    "in-review": "Claude done / In review (Dolev)",
    "done": "Done",
    "backlog": "Backlog",
}
# Older boards (CRM, business-plan-generator, OSEA) name this option "Plan questions (Dolev)".
# Rewriting a board's options clears the value on every card, so the script adapts instead.
STATUS_ALIASES = {"plan-questions": ("Plan questions", "Plan questions (Dolev)")}
# Filled from the board by resolve_options: each repo has its own areas, and the option name
# is the label suffix with its own capitalisation (area:seo <-> SEO), a dev-setup convention.
AREA_OPTIONS = {}

DIMENSIONS = [
    ("owner", "Owner", OWNER_OPTIONS),
    ("status", "Status", STATUS_OPTIONS),
    ("area", "Area", AREA_OPTIONS),
]


def gh(*args):
    p = subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if p.returncode != 0:
        raise RuntimeError("gh %s failed: %s" % (" ".join(args[:3]), p.stderr.strip()))
    return p.stdout


def graphql(query, **variables):
    args = ["api", "graphql", "-f", "query=" + query]
    for k, v in variables.items():
        # -F turns anything that looks like a number into one, and an option id can be all
        # digits ("84237580"), which GitHub then rejects as a String!. Only ints get -F.
        flag = "-F" if isinstance(v, int) else "-f"
        args += [flag, "%s=%s" % (k, v)]
    out = json.loads(gh(*args))
    # A GraphQL error can arrive with a 200, which gh reports as success. Without this
    # check a failed mutation looks like a successful sync.
    if out.get("errors"):
        raise RuntimeError(json.dumps(out["errors"], ensure_ascii=False)[:800])
    return out


# --------------------------------------------------------------------------- project

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


def load_project(number):
    data = graphql(PROJECT_QUERY, owner=PROJECT_OWNER, number=number)["data"]["user"]["projectV2"]
    fields = {f["name"]: f for f in data["fields"]["nodes"] if f.get("name")}

    repo_owner, repo_name = REPO.split("/", 1)
    by_issue = {}
    after = None
    while True:
        kw = {"owner": repo_owner, "repo": repo_name}
        if after:
            kw["after"] = after
        page = graphql(ISSUE_ITEMS, **kw)["data"]["repository"]["issues"]
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
    return data["id"], fields, by_issue, data["views"]["nodes"]


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


def resolve_options(fields):
    """Fit AREA_OPTIONS and STATUS_OPTIONS to this board's actual option names."""
    area = fields.get("Area") or {}
    AREA_OPTIONS.clear()
    AREA_OPTIONS.update({o["name"].lower(): o["name"] for o in area.get("options", [])})
    names = {o["name"] for o in (fields.get("Status") or {}).get("options", [])}
    for suffix, aliases in STATUS_ALIASES.items():
        STATUS_OPTIONS[suffix] = next((a for a in aliases if a in names), aliases[0])


def doubled_dimensions(labels):
    """The dimensions an issue carries more than one label of, e.g. two status:* labels.

    Which one is meant cannot be told, and either guess would be written to the board and
    into the marker as if it were the truth (OSEA, 2026-10-24).
    """
    return [k for k, _, _ in DIMENSIONS if sum(l.startswith(k + ":") for l in labels) > 1]


def set_field(project_id, item_id, field, option_name):
    option = next((o for o in field.get("options", []) if o["name"] == option_name), None)
    if option is None:
        print("  ! field %r has no option %r - skipped" % (field["name"], option_name))
        return
    graphql(SET_SELECT, project=project_id, item=item_id, field=field["id"], option=option["id"])


# ------------------------------------------------------------------------ sprint view

SPRINT_VIEW = "ספרינט נוכחי"
MILESTONE_TERM = re.compile(r'milestone:(?:"[^"]*"|\S+)')

UPDATE_VIEW_FILTER = """
mutation($view:ID!, $filter:String!) {
  updateProjectV2View(input:{viewId:$view, filter:$filter}) { projectV2View { id } }
}
"""


def current_sprint(milestones):
    """The lowest-numbered open milestone with open issues, as pipeline_info.py reads it."""
    with_issues = sorted((m for m in milestones if m["open_issues"] > 0), key=lambda m: m["number"])
    return with_issues[0]["title"] if with_issues else None


def sprint_view_change(views, sprint):
    """(view id, new filter) when the sprint view shows another milestone, else None."""
    view = next((v for v in views if v["name"] == SPRINT_VIEW), None)
    if not sprint or not view or not MILESTONE_TERM.search(view["filter"] or ""):
        return None
    wanted = MILESTONE_TERM.sub(lambda _: 'milestone:"%s"' % sprint, view["filter"], count=1)
    return (view["id"], wanted) if wanted != view["filter"] else None


def sync_sprint_view(views):
    milestones = json.loads(gh("api", "repos/%s/milestones?state=open&per_page=100" % REPO))
    change = sprint_view_change(views, current_sprint(milestones))
    if change:
        graphql(UPDATE_VIEW_FILTER, view=change[0], filter=change[1])
        print("sprint view -> %s" % change[1])


# ---------------------------------------------------------------------------- issues


def read_marker(body):
    m = MARKER_RE.search(body or "")
    if not m:
        return {}
    out = {}
    for pair in m.group(1).split():
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k] = v
    return out


def write_marker(body, state):
    payload = " ".join("%s=%s" % (k, v) for k, v in sorted(state.items()) if v)
    marker = "<!-- %s: %s -->" % (SYNC_MARKER, payload)
    body = body or ""
    if MARKER_RE.search(body):
        return MARKER_RE.sub(marker, body)
    return body.rstrip() + "\n\n" + marker + "\n"


def labels_state(labels):
    state = {}
    for key, _field, options in DIMENSIONS:
        for name in labels:
            if name.startswith(key + ":"):
                suffix = name.split(":", 1)[1]
                if suffix in options:
                    state[key] = suffix
                break
    return state


def project_state(values):
    state = {}
    for key, field_name, options in DIMENSIONS:
        shown = values.get(field_name)
        if not shown:
            continue
        for suffix, option_name in options.items():
            if option_name == shown:
                state[key] = suffix
                break
    return state


def choose_winner(marker, from_labels, from_project):
    """Return (state, source) for the side that changed, or (None, None) if in agreement.

    A blank board with a marker that matches the labels means the fields were never
    written (e.g. an issue created with the marker already in its body). Without the
    second check such an item would stay blank on the board forever.
    """
    if from_project and from_project != marker:
        return from_project, "project"
    if from_labels != marker or (from_labels and not from_project):
        return from_labels, "labels"
    return None, None


def edit_body(number, new_body):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8", newline="\n")
    f.write(new_body)
    f.close()
    try:
        gh("issue", "edit", str(number), "--repo", REPO, "--body-file", f.name)
    finally:
        os.unlink(f.name)


def check_environment():
    """Fail loudly on a missing token or project number.

    `gh secret set` cannot tell an empty paste from a real one, so a secret that was
    never actually pasted still reports success and then arrives here as an empty
    string. Without this check the first symptom is a gh usage message buried in a
    traceback, which reads like a bug in this script rather than a missing secret.
    """
    if not os.environ.get("GH_TOKEN", "").strip():
        raise SystemExit(
            "GH_TOKEN is empty. The PROJECT_TOKEN secret is unset or was stored empty.\n"
            "Set it again with:  $t = Read-Host 'Paste token'; "
            "gh secret set PROJECT_TOKEN --body $t; Remove-Variable t"
        )
    if not os.environ.get("PROJECT_NUMBER", "").strip():
        raise SystemExit(
            "PROJECT_NUMBER is empty. Set the repository variable:  gh variable set PROJECT_NUMBER --body 1"
        )
    if not SYNC_MARKER:
        raise SystemExit(
            "SYNC_MARKER is empty. Set it to the marker name the issue bodies already carry\n"
            "(e.g. crm-sync):  gh variable set SYNC_MARKER --body <name>"
        )


def main():
    check_environment()
    number = int(os.environ["PROJECT_NUMBER"])
    only = os.environ.get("ISSUE_NUMBER", "").strip()

    project_id, fields, project_items, views = load_project(number)
    resolve_options(fields)
    try:
        sync_sprint_view(views)
    except RuntimeError as e:
        print("! sprint view not updated: %s" % e)

    issues = json.loads(
        gh(
            "issue", "list", "--repo", REPO, "--state", "all", "--limit", "500",
            "--json", "number,body,labels,id,state",
        )
    )
    if only:
        issues = [i for i in issues if i["number"] == int(only)]

    for issue in issues:
        num = issue["number"]
        labels = [l["name"] for l in issue["labels"]]
        if not any(l.startswith("owner:") or l.startswith("status:") for l in labels):
            continue  # not a pipeline issue - leave it alone
        if issue["state"].upper() == "CLOSED" and "status:done" not in labels:
            continue  # closed as not-planned - it does not belong on the board
        doubled = doubled_dimensions(labels)
        if doubled:
            print("! #%s has more than one %s label - skipped" % (num, "/".join(doubled)))
            continue

        item = project_items.get(num)
        if item is None:
            res = graphql(ADD_ITEM, project=project_id, content=issue["id"])
            item = {"id": res["data"]["addProjectV2ItemById"]["item"]["id"], "values": {}}
            print("#%s added to the project" % num)

        marker = read_marker(issue["body"])
        from_labels = labels_state(labels)
        from_project = project_state(item["values"])

        winner, source = choose_winner(marker, from_labels, from_project)
        if source is None:
            continue  # already in agreement

        if source == "project":
            keep = [l for l in labels if not any(l.startswith(k + ":") for k, _, _ in DIMENSIONS)]
            desired = keep + ["%s:%s" % (k, v) for k, v in winner.items()]
            args = []
            for l in desired:
                if l not in labels:
                    args += ["--add-label", l]
            for l in labels:
                if l not in desired:
                    args += ["--remove-label", l]
            if args:
                gh("issue", "edit", str(num), "--repo", REPO, *args)
                print("#%s labels <- project: %s" % (num, winner))
        else:
            for key, field_name, options in DIMENSIONS:
                suffix = winner.get(key)
                if not suffix or item["values"].get(field_name) == options[suffix]:
                    continue
                field = fields.get(field_name)
                if field is None:
                    print("  ! the project has no field %r - skipped" % field_name)
                    continue
                set_field(project_id, item["id"], field, options[suffix])
            print("#%s project <- labels: %s" % (num, winner))

        new_body = write_marker(issue["body"], winner)
        if new_body != (issue["body"] or ""):
            edit_body(num, new_body)


if __name__ == "__main__":
    sys.exit(main())
