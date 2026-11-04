"""The shared open-questions gate in dev-setup/actions (claude-config #2).

Every repo with the pipeline runs this one copy, so these tests guard all of them.
"""

import importlib.util
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / "actions" / "open-questions-gate"
TEMPLATE = ROOT / "templates" / ".github" / "workflows" / "open-questions-gate.yml"
os.environ.setdefault("GITHUB_REPOSITORY", "dolev2/example")


def load_gate():
    spec = importlib.util.spec_from_file_location(
        "check_open_questions", ACTION / "check_open_questions.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gate_reads_checkboxes():
    gate = load_gate()
    assert gate.open_questions("### שאלות פתוחות\n- [ ] a?\n- [x] b\n### Next\n") == [
        "a?"
    ]


def test_gate_checkboxes_ignore_the_sync_marker():
    body = (
        "### שאלות פתוחות\n- [ ] a?\n- [x] b — הוחלט\n\n"
        "<!-- crm-sync: status=plan-questions -->\n"
    )
    assert load_gate().open_questions(body) == ["a?"]


def test_gate_reads_the_last_section_not_the_plans():
    gate = load_gate()
    body = (
        "## Plan\n### Open questions\nאין.\n### Approach\nx\n"
        "## שאלות פתוחות\n- [ ] real?\n"
    )
    assert gate.open_questions(body) == ["real?"]


def test_gate_issue_section_wins_over_a_deeper_plan_subsection():
    body = "### Plan\n#### שאלות פתוחות\nאין.\n### שאלות פתוחות\n- [ ] real?\n"
    assert load_gate().open_questions(body) == ["real?"]


def test_gate_section_runs_past_lower_headings():
    gate = load_gate()
    body = "## שאלות פתוחות\n### Pricing\n- [ ] price?\n## Next\n- [ ] not here\n"
    assert gate.open_questions(body) == ["price?"]


def test_gate_legacy_section_skips_the_sync_marker():
    gate = load_gate()
    body = "### שאלות פתוחות\nlegacy question\n\n<!-- crm-sync: status=plan-questions -->\n"
    assert gate.open_questions(body) == ["legacy question"]


def test_gate_section_with_only_a_placeholder_and_the_marker_is_clear():
    # CRM #55: the body of CRM #48 when it moved to status:done.
    gate = load_gate()
    body = (
        "### Plan\n\nplan text\n\n### שאלות פתוחות\n\n_אין שאלות פתוחות._\n\n"
        "<!-- crm-sync: status=done -->\n"
    )
    assert gate.open_questions(body) == []


def test_gate_warning_names_the_section_as_the_issue_spells_it():
    gate = load_gate()
    body = "## Goal\nx\n## Open questions\n- [ ] which currency?\n"
    heading, _ = gate.find_section(body)
    text = gate.warning(heading, gate.open_questions(body))
    assert '"Open questions"' in text
    assert "- which currency?" in text
    assert '"שאלות פתוחות"' in gate.warning(
        gate.find_section("### שאלות פתוחות\n- [ ] a\n")[0], ["a"]
    )


def test_action_runs_a_script_that_exists():
    # A rename here would break the gate in every repo at once, silently.
    action = (ACTION / "action.yml").read_text(encoding="utf-8")
    assert "using: composite" in action
    scripts = re.findall(r"\$\{\{ github\.action_path \}\}/([\w./-]+\.py)", action)
    assert scripts, "action.yml no longer runs a script from its own folder"
    for script in scripts:
        assert (ACTION / script).is_file(), script


def test_template_calls_the_shared_action_at_main_without_checkout():
    workflow = TEMPLATE.read_text(encoding="utf-8")
    assert (
        "uses: dolev2/claude-config/skills/dev-setup/actions/open-questions-gate@main"
        in workflow
    )
    assert "actions/checkout" not in workflow
    assert "check_open_questions.py" not in workflow.split("jobs:")[1]


def test_no_copy_of_the_gate_script_is_left_to_install():
    assert not (
        ROOT / "templates" / ".github" / "scripts" / "check_open_questions.py"
    ).exists()


def test_home_repo_workflow_can_read_its_own_action():
    # The run in claude-config itself downloads the action with GITHUB_TOKEN
    # (claude-config #9).
    workflow = (
        ROOT.parents[1] / ".github" / "workflows" / "open-questions-gate.yml"
    ).read_text(encoding="utf-8")
    assert "contents: read" in workflow
    assert (
        "uses: dolev2/claude-config/skills/dev-setup/actions/open-questions-gate@main"
        in workflow
    )
