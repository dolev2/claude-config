"""spec_changes.py and spec_check.py --changes: the parts that changed, their issues."""

import subprocess
import sys
from pathlib import Path

import pytest
import spec_changes
import spec_check
from spec_changes import Change

SPEC = "docs/specs/pipeline.md"
BASE = """# Pipeline

## Stage one

### S-1.1 · Read the spec
**מצב:** פתוח (#5)

Reads the spec.

### S-1.2 · Write the table
**מצב:** Done (#12)

Writes the table.

##### A detail
One detail.

### S-1.3 · Old part
**מצב:** פתוח (#7)

Goes away.
"""


def changed(old: str, new: str) -> list[Change]:
    """compare() on one file, at SPEC, before and after."""
    return spec_changes.compare({SPEC: old}, {SPEC: new})


def test_same_text_is_no_change():
    assert changed(BASE, BASE) == []


@pytest.mark.parametrize(
    "old, new",
    [
        ("Reads the spec.", "Reads the spec, twice."),
        ("### S-1.1 · Read the spec", "### S-1.1 · Read the whole spec"),
        ("One detail.", "Two details."),
    ],
    ids=["text", "name", "sub-heading inside a part"],
)
def test_a_change_counts(old, new):
    found = changed(BASE, BASE.replace(old, new))
    assert [change.kind for change in found] == ["changed"]


def test_the_change_carries_the_new_name():
    new = BASE.replace("Read the spec", "Read the whole spec")
    assert changed(BASE, new) == [
        Change("changed", SPEC, "S-1.1", "Read the whole spec")
    ]


@pytest.mark.parametrize(
    "old, new",
    [
        ("**מצב:** פתוח (#5)", "**מצב:** Done (#5)"),
        ("**מצב:** פתוח (#7)\n", ""),
        ("Reads the spec.", "Reads the spec (שופר ב-#242)."),
        ("Reads the spec.", "Reads the spec, שופר ב-#242, #243."),
        ("Reads the spec.", "Reads the spec (שופר ב-#5 ו-#6)."),
        ("Reads the spec.", "Reads the spec.   "),
        ("Reads the spec.", "\n\nReads the spec.\n\n"),
    ],
    ids=[
        "status",
        "status removed",
        "improved",
        "improved bare",
        "improved and",
        "spaces",
        "blanks",
    ],
)
def test_what_does_not_count(old, new):
    assert changed(BASE, BASE.replace(old, new)) == []


def test_a_level_five_id_heading_belongs_to_its_part():
    new = BASE.replace("##### A detail", "##### S-1.9 · A detail")
    assert changed(BASE, new) == [Change("changed", SPEC, "S-1.2", "Write the table")]


def test_new_and_deleted_parts():
    new = BASE.replace("### S-1.3 · Old part", "### S-1.4 · New part")
    assert changed(BASE, new) == [
        Change("new", SPEC, "S-1.4", "New part"),
        Change("deleted", SPEC, "S-1.3", "Old part"),
    ]


def test_an_example_in_a_code_block_is_no_part():
    new = BASE + "\n```markdown\n### S-1.9 · an example\n```\n"
    assert changed(BASE, new) == [Change("changed", SPEC, "S-1.3", "Old part")]


@pytest.mark.parametrize(
    "old, new, kinds",
    [({}, {SPEC: BASE}, ["new"] * 3), ({SPEC: BASE}, {}, ["deleted"] * 3)],
    ids=["no file before", "no file after"],
)
def test_a_missing_file(old, new, kinds):
    found = spec_changes.compare(old, new)
    assert [change.kind for change in found] == kinds


def test_a_part_that_moved_file_is_deleted_and_new():
    found = spec_changes.compare({SPEC: BASE}, {"docs/specs/other.md": BASE})
    assert [change.kind for change in found] == ["new"] * 3 + ["deleted"] * 3


@pytest.mark.parametrize(
    "label",
    [
        "status:explore",
        "status:plan-questions",
        "status:waiting-approval",
        "status:ready-to-execute",
    ],
)
def test_a_changed_part_before_the_code_goes_back_to_explore(label):
    assert spec_changes.action("changed", {label, "task"}) == "explore"


@pytest.mark.parametrize(
    "labels", [{"status:needs-repair"}, {"status:in-review"}, set()]
)
def test_a_changed_part_in_the_code_or_without_status_asks(labels):
    assert spec_changes.action("changed", labels) == "ask"


@pytest.mark.parametrize(
    "labels", [{"status:explore"}, {"status:in-review"}, {"status:backlog"}, set()]
)
def test_a_deleted_part_closes_in_every_state(labels):
    assert spec_changes.action("deleted", labels) == "close"


def test_a_new_part_has_no_action():
    assert spec_changes.action("new", {"status:explore"}) is None


def issue(number: int, *labels: str) -> dict:
    """An open issue as fetch_issues returns it, without a body."""
    return {"number": number, "labels": set(labels), "body": ""}


def test_report_lists_the_issues_under_each_part():
    changes = [
        Change("changed", SPEC, "S-1.1", "Read"),
        Change("deleted", SPEC, "S-1.3", "Old"),
        Change("new", SPEC, "S-1.4", "New"),
        Change("new", SPEC, "S-1.5", "Taken"),
    ]
    pointed = {
        (SPEC, "S-1.1"): [issue(9, "status:in-review"), issue(5, "status:explore")],
        (SPEC, "S-1.3"): [issue(7)],
        (SPEC, "S-1.5"): [issue(8, "status:explore")],
    }
    assert spec_changes.report(changes, pointed) == [
        "changed S-1.1 · Read",
        "  #5 status:explore -> explore",
        "  #9 status:in-review -> ask",
        "deleted S-1.3 · Old",
        "  #7 no status -> close",
        "new S-1.4 · New",
    ]


def test_report_without_issues_lists_every_part():
    changes = [Change("new", SPEC, "S-1.4", "New")]
    assert spec_changes.report(changes, None) == ["new S-1.4 · New"]


def test_report_with_no_change():
    assert spec_changes.report([], {}) == ["no spec changes"]


def run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A git repo: the tag `base` holds BASE, HEAD has S-1.1 changed."""
    run_git(tmp_path, "init", "-q")
    run_git(tmp_path, "config", "user.email", "test@example.com")
    run_git(tmp_path, "config", "user.name", "test")
    spec = tmp_path / SPEC
    spec.parent.mkdir(parents=True)
    spec.write_text(BASE, encoding="utf-8")
    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-q", "-m", "base")
    run_git(tmp_path, "tag", "base")
    spec.write_text(BASE.replace("Reads the spec.", "Reads it all."), encoding="utf-8")
    run_git(tmp_path, "commit", "-q", "-am", "head")
    return tmp_path


def test_changes_run_without_issues(repo):
    done = subprocess.run(
        [sys.executable, str(Path(spec_check.__file__)), "--root", str(repo)]
        + ["--changes", "base", "HEAD", "--no-issues"],
        capture_output=True,
        encoding="utf-8",
    )
    assert done.returncode == 0
    assert done.stdout == "changed S-1.1 · Read the spec\n"


def test_changes_with_the_issues(repo, monkeypatch, capsys):
    body = f"### הקשר / קישורים\nאפיון: {SPEC} S-1.1\n"
    found = [{"number": 5, "labels": {"status:ready-to-execute"}, "body": body}]
    monkeypatch.setattr(spec_check, "fetch_issues", lambda repo: found)
    code = spec_check.main(["--root", str(repo), "--changes", "base", "HEAD"])
    assert code == 0
    assert capsys.readouterr().out.splitlines() == [
        "changed S-1.1 · Read the spec",
        "  #5 status:ready-to-execute -> explore",
    ]


def test_changes_with_unread_issues_warn_and_fail(repo, monkeypatch, capsys):
    def fail(repo):
        raise SystemExit("gh failed")

    monkeypatch.setattr(spec_check, "fetch_issues", fail)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    code = spec_check.main(["--root", str(repo), "--changes", "base", "HEAD"])
    out = capsys.readouterr().out
    assert code == 1
    assert "warning: issues not read: gh failed" in out
    assert "changed S-1.1 · Read the spec" in out


def test_changes_unknown_ref_exits_with_the_reason(repo):
    with pytest.raises(SystemExit) as stop:
        spec_check.main(["--root", str(repo), "--changes", "nope", "HEAD"])
    assert "spec files not read" in str(stop.value.code)
