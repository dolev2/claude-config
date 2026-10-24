"""The .github/scripts templates that dev-setup copies into a repo."""

import importlib.util
import os
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "templates" / ".github" / "scripts"
os.environ.setdefault("GITHUB_REPOSITORY", "dolev2/example")


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sync_marker_name_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("SYNC_MARKER", "crm-sync")
    sync = load("sync_project")
    body = "text\n\n<!-- crm-sync: owner=claude status=explore -->\n"
    assert sync.read_marker(body) == {"owner": "claude", "status": "explore"}
    assert sync.write_marker(body, {"status": "done"}).endswith("<!-- crm-sync: status=done -->\n")
    assert sync.read_marker("<!-- wayout-sync: owner=claude -->") == {}
    assert sync.PROJECT_OWNER == "dolev2"


def test_sync_marker_defaults_to_pipeline_sync(monkeypatch):
    monkeypatch.delenv("SYNC_MARKER", raising=False)
    sync = load("sync_project")
    assert sync.write_marker("x", {"owner": "claude"}).endswith("<!-- pipeline-sync: owner=claude -->\n")


def test_gate_reads_checkboxes():
    gate = load("check_open_questions")
    assert gate.open_questions("### שאלות פתוחות\n- [ ] a?\n- [x] b\n### Next\n") == ["a?"]


def test_gate_reads_the_last_section_not_the_plans():
    gate = load("check_open_questions")
    body = "## Plan\n### Open questions\nאין.\n### Approach\nx\n## שאלות פתוחות\n- [ ] real?\n"
    assert gate.open_questions(body) == ["real?"]


def test_gate_section_runs_past_lower_headings():
    gate = load("check_open_questions")
    body = "## שאלות פתוחות\n### Pricing\n- [ ] price?\n## Next\n- [ ] not here\n"
    assert gate.open_questions(body) == ["price?"]


def test_gate_legacy_section_skips_the_sync_marker():
    gate = load("check_open_questions")
    body = "### שאלות פתוחות\nlegacy question\n\n<!-- crm-sync: owner=dolev -->\n"
    assert gate.open_questions(body) == ["legacy question"]
