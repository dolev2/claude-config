"""The rules of the board sync: which issues take part, and what is written where.

One way, from the labels to the board
-------------------------------------
The labels are the source of truth and the board only mirrors them (claude-config
#106, #111). Every dimension the labels carry is written to the board when the board
shows something else, so a card dragged by hand goes back on the next sync. A
dimension with no label is left as the board has it. There is no hidden marker and no
rule for choosing a side: nothing is compared but the labels and the board.

The one exception: an issue with no status:* label at all, which was opened from the
board past the issue form, takes its labels from its card once (WayOut #98,
claude-config #55). From then on its labels rule like any other's.

A decision issue is not that exception: it has no status:* label by design (dev-issue),
so a column left on its card from before is cleared, not copied back into a label
(claude-config #128).

There is no owner dimension: the status alone says whose turn it is
(claude-config #110).

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
    as if it were the truth (OSEA, 2026-10-24).
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


def board_changes(
    from_labels: dict[str, str], from_project: dict[str, str]
) -> dict[str, str]:
    """The dimensions whose label the board does not show yet, with the label's value.

    A dimension with no label is not in the result, so the board keeps its value.
    """
    return {
        key: value
        for key, value in from_labels.items()
        if from_project.get(key) != value
    }


def labels_from_board(
    labels: list[str], from_project: dict[str, str]
) -> dict[str, str]:
    """The state an issue with no status:* label takes from its card; empty otherwise.

    Only a card that shows a status counts. A label the issue already carries (an
    area, say) is kept over the card's value.
    """
    if any(label.startswith("status:") for label in labels):
        return {}
    if "decision" in labels:
        return {}  # no status by design; see clears_status
    if "status" not in from_project:
        return {}
    return {**from_project, **labels_state(labels)}


def clears_status(labels: list[str], values: dict[str, str]) -> bool:
    """Whether a decision issue's card still shows a column that must be cleared.

    A task that became a decision loses its status:* label, and its card keeps the
    last column. Left there, the card would be read as the issue's status (zohar
    #27, #31). values are the card's raw field values, so a column the sync does not
    know (a board's default "Todo") is cleared too. With a status:* label on it the
    labels rule as usual.
    """
    return (
        "decision" in labels
        and not any(label.startswith("status:") for label in labels)
        and bool(values.get("Status"))
    )


def label_edit_args(labels: list[str], state: dict[str, str]) -> list[str]:
    """The `gh issue edit` flags that turn labels into state.

    Labels outside the dimensions (task, bug, process, ...) are kept.
    """
    keep = [
        label
        for label in labels
        if not any(label.startswith(k + ":") for k, _, _ in DIMENSIONS)
    ]
    desired = keep + [f"{k}:{v}" for k, v in state.items()]
    args = []
    for label in desired:
        if label not in labels:
            args += ["--add-label", label]
    for label in labels:
        if label not in desired:
            args += ["--remove-label", label]
    return args


def is_pipeline_issue(labels: list[str]) -> bool:
    """Whether the labels mark a pipeline issue: a status:* label, or a decision.

    A decision issue carries no status; until #110 its owner: label made it one.
    """
    return "decision" in labels or any(label.startswith("status:") for label in labels)


def should_sync(labels: list[str], state: str, on_board: bool) -> bool:
    """Whether the issue takes part in the sync at all.

    An issue with no status: label is still synced when it is on the board: it
    was opened from the board, past the issue form, and its column is the only state it
    has (WayOut #98 sat a month like that, claude-config #55).
    """
    if not on_board and not is_pipeline_issue(labels):
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
        and is_pipeline_issue(labels)
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
