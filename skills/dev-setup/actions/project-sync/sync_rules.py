"""The rules of the board sync: which issues take part, and which side wins.

Conflict resolution
-------------------
On each run three states are compared: the issue body's marker (marker.py), its labels,
and its board item. Whichever of labels or project differs from the marker is the side
that changed and therefore wins; if both changed, the project wins, because that edit
was a deliberate human drag while a label may have been set by an earlier automated
step. A board item with no Status/Area at all always takes the labels, even when
they match the marker. The winner is then written to the other side and the marker is
rewritten.

There is no owner dimension: the status alone says whose turn it is
(claude-config #110). A marker written before that still carries `owner=`;
choose_winner ignores it.

Nothing here talks to GitHub: every function takes and returns plain values.
"""

# label suffix  ->  the option name as it appears in the Project's single-select field
STATUS_OPTIONS = {
    "explore": "Explore (Claude)",
    "plan-questions": "Plan questions",  # or a name from STATUS_ALIASES, per board
    "waiting-approval": "Waiting for Dolev approval",
    "ready-to-execute": "Ready to execute (Claude)",
    "needs-repair": "Needs repair (Claude)",
    "in-review": "Claude done / In review (Dolev)",
    "done": "Done",
    "backlog": "Backlog",
}
# Older boards (CRM, business-plan-generator, OSEA) name this option
# "Plan questions (Dolev)". Rewriting a board's options clears the value on every card,
# so the script adapts instead.
STATUS_ALIASES = {"plan-questions": ("Plan questions", "Plan questions (Dolev)")}
# Filled from the board by resolve_options: each repo has its own areas, and the option
# name is the label suffix with its own capitalisation (area:seo <-> SEO), a dev-setup
# convention.
AREA_OPTIONS: dict[str, str] = {}

DIMENSIONS = [
    ("status", "Status", STATUS_OPTIONS),
    ("area", "Area", AREA_OPTIONS),
]


def resolve_options(fields: dict) -> None:
    """Fit AREA_OPTIONS and STATUS_OPTIONS to this board's actual option names."""
    area = fields.get("Area") or {}
    AREA_OPTIONS.clear()
    AREA_OPTIONS.update({o["name"].lower(): o["name"] for o in area.get("options", [])})
    names = {o["name"] for o in (fields.get("Status") or {}).get("options", [])}
    for suffix, aliases in STATUS_ALIASES.items():
        STATUS_OPTIONS[suffix] = next((a for a in aliases if a in names), aliases[0])


def doubled_dimensions(labels: list[str]) -> list[str]:
    """The dimensions an issue carries more than one label of, e.g. two status:* labels.

    Which one is meant cannot be told, and either guess would be written to the board
    and into the marker as if it were the truth (OSEA, 2026-10-24).
    """
    return [
        key
        for key, _, _ in DIMENSIONS
        if sum(label.startswith(key + ":") for label in labels) > 1
    ]


def labels_state(labels: list[str]) -> dict[str, str]:
    """The status/area state the labels express."""
    state = {}
    for key, _field, options in DIMENSIONS:
        for name in labels:
            if name.startswith(key + ":"):
                suffix = name.split(":", 1)[1]
                if suffix in options:
                    state[key] = suffix
                break
    return state


def project_state(values: dict[str, str]) -> dict[str, str]:
    """The status/area state the board item's field values express."""
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


def choose_winner(
    marker: dict[str, str],
    from_labels: dict[str, str],
    from_project: dict[str, str],
) -> tuple[dict[str, str] | None, str | None]:
    """(state, source) for the side that changed, or (None, None) if in agreement.

    A blank board with a marker that matches the labels means the fields were never
    written (e.g. an issue created with the marker already in its body). Without the
    second check such an item would stay blank on the board forever.

    Keys outside DIMENSIONS (an old `owner=`) are dropped from the marker first, or
    every issue would look changed on both sides and the board would win over a fresh
    label.
    """
    marker = {k: v for k, v in marker.items() if k in {key for key, _, _ in DIMENSIONS}}
    if from_project and from_project != marker:
        return from_project, "project"
    if from_labels != marker or (from_labels and not from_project):
        return from_labels, "labels"
    return None, None


def label_edit_args(labels: list[str], winner: dict[str, str]) -> list[str]:
    """The `gh issue edit` flags that turn labels into the winner's state.

    Labels outside the dimensions (task, bug, process, ...) are kept.
    """
    keep = [
        label
        for label in labels
        if not any(label.startswith(k + ":") for k, _, _ in DIMENSIONS)
    ]
    desired = keep + [f"{k}:{v}" for k, v in winner.items()]
    args = []
    for label in desired:
        if label not in labels:
            args += ["--add-label", label]
    for label in labels:
        if label not in desired:
            args += ["--remove-label", label]
    return args


def should_sync(labels: list[str], state: str, on_board: bool) -> bool:
    """Whether the issue takes part in the sync at all.

    An issue with no status: label is still synced when it is on the board: it
    was opened from the board, past the issue form, and its column is the only state it
    has (WayOut #98 sat a month like that, claude-config #55).
    """
    if not on_board and not any(label.startswith("status:") for label in labels):
        return False  # not a pipeline issue - leave it alone
    # Closed as not-planned: it does not belong on the board.
    return state.upper() != "CLOSED" or "status:done" in labels


def needs_done_label(labels: list[str], state: str, state_reason: str | None) -> bool:
    """Whether a closed pipeline issue was completed but keeps an earlier status.

    A PR merged with `Closes #N` closes the issue as COMPLETED and leaves its
    status:in-review label, so should_sync would take it for not-planned and the card
    would never reach Done (claude-config #97: 11 issues in three repos).
    """
    return (
        state.upper() == "CLOSED"
        and (state_reason or "").upper() == "COMPLETED"
        and "status:done" not in labels
        and any(label.startswith("status:") for label in labels)
    )


def done_labels(labels: list[str]) -> list[str]:
    """The labels with every status:* label replaced by status:done."""
    return [label for label in labels if not label.startswith("status:")] + [
        "status:done"
    ]


def is_active_without_sprint(issue: dict, labels: list[str]) -> bool:
    """An open issue in the pipeline (not backlog, not done) that has no milestone.

    Only a warning: an issue Dolev names may be planned outside every sprint.
    """
    status = next((label for label in labels if label.startswith("status:")), None)
    return (
        issue["state"].upper() == "OPEN"
        and status not in (None, "status:backlog", "status:done")
        and not issue.get("milestone")
    )
