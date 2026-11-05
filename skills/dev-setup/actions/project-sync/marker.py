"""The hidden marker in each issue body: the state at the end of the last sync.

    <!-- <SYNC_MARKER>: area=backend status=explore -->

The marker name differs per repo (crm-sync, wayout-sync, ...) and comes from
SYNC_MARKER; sync_project.check_environment stops the run when it is empty. Never
rename it once issues carry it: a body whose marker is not found looks like it was never
synced.
"""

import re


def marker_pattern(name: str) -> re.Pattern:
    """The regex that finds the marker called name; group 1 is its payload."""
    return re.compile(r"<!--\s*" + re.escape(name) + r":(.*?)-->", re.S)


def read_marker(body: str | None, name: str) -> dict[str, str]:
    """The state recorded in the body's sync marker; empty without a marker."""
    m = marker_pattern(name).search(body or "")
    if not m:
        return {}
    out = {}
    for pair in m.group(1).split():
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k] = v
    return out


def write_marker(body: str | None, state: dict[str, str], name: str) -> str:
    """The body with its sync marker set to state, added at the end when missing."""
    payload = " ".join(f"{k}={v}" for k, v in sorted(state.items()) if v)
    marker = f"<!-- {name}: {payload} -->"
    body = body or ""
    pattern = marker_pattern(name)
    if pattern.search(body):
        return pattern.sub(marker, body)
    return body.rstrip() + "\n\n" + marker + "\n"
