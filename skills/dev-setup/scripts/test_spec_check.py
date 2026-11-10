"""spec_check.py: the errors in a spec file, the gaps against the issues, the table."""

import subprocess
import sys
from pathlib import Path

import pytest
import spec_check
from spec_check import Part

SCRIPT = Path(__file__).resolve().parent / "spec_check.py"
VALID = """# Pipeline

## Stage one
Free grouping, no part.

### S-1.1 · Read the spec
Text.

### S-1.2 · Write the table
**מצב:** Done (#12)

### S-1.3 · Old idea
**מצב:** מחוץ להיקף

```markdown
## S-1.1 · an example inside a code block is no part
```
"""
SPEC = "docs/specs/pipeline.md"


def issue(number: int, body: str = "", *labels: str) -> dict:
    """An open issue as fetch_issues returns it."""
    return {"number": number, "labels": set(labels), "body": body}


def pointing(number: int, ids: str, *labels: str) -> dict:
    """An open issue whose context section points at `ids` in the spec."""
    body = f"### מה רוצים\nx\n\n### הקשר / קישורים\nאפיון: {SPEC} {ids}\n"
    return issue(number, body, *labels)


def test_valid_spec_parts_and_statuses():
    parts, errors = spec_check.parse_spec(VALID)
    assert errors == []
    assert parts == [
        Part("S-1.1", "Read the spec", 6),
        Part("S-1.2", "Write the table", 9, "done", 12),
        Part("S-1.3", "Old idea", 12, "out"),
    ]


def test_empty_spec_has_no_parts():
    assert spec_check.parse_spec("") == ([], [])


@pytest.mark.parametrize(
    "text, expected",
    [
        ("## S-1.1 · a\n\n## S-1.1 · b\n", "duplicate id S-1.1 (first at line 1)"),
        ("## S-3 · no minor\n", "broken part heading"),
        ("## S-3.x · not a number\n", "broken part heading"),
        ("##### S-3.1 · too deep\n", "is at level 5"),
        (
            "## S-3.1 · a\n**מצב:** בעבודה\n",
            "unknown status line '**מצב:** בעבודה' under S-3.1",
        ),
    ],
)
def test_file_errors(text, expected):
    _, errors = spec_check.parse_spec(text)
    assert len(errors) == 1
    assert expected in errors[0][1]


def test_spec_files_skip_readme(tmp_path):
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("## S-1 broken on purpose\n", encoding="utf-8")
    (folder / "pipeline.md").write_text(VALID, encoding="utf-8")
    assert list(spec_check.spec_files(tmp_path)) == [SPEC]


def test_no_specs_folder(tmp_path):
    assert spec_check.spec_files(tmp_path) == {}


SPECS = {SPEC: spec_check.parse_spec(VALID)[0]}


@pytest.mark.parametrize(
    "found, expected",
    [
        (pointing(5, "S-9.9"), f"#5 points at {SPEC} S-9.9: no such part"),
        (
            issue(5, "### הקשר / קישורים\nאפיון: docs/specs/gone.md S-1.1\n"),
            "#5 points at docs/specs/gone.md: no such spec file",
        ),
        (issue(5, "### הקשר / קישורים\nאפיון: S-1.1\n"), "has no file"),
        (issue(5, "### הקשר / קישורים\nתלוי ב: אין\n"), "#5 has no spec line"),
    ],
)
def test_issue_gaps(found, expected):
    messages = [gap.message for gap in spec_check.issue_gaps(SPECS, found)]
    assert len(messages) == 1
    assert expected in messages[0]


def test_a_bug_names_its_part_in_its_plan():
    body = f"### מה קורה\nx\n\n### Plan\n- **אפיון:** {SPEC} S-1.1\n"
    assert spec_check.issue_gaps(SPECS, issue(5, body, "bug")) == []


def test_the_context_line_wins_over_the_plan_line():
    body = (
        f"### הקשר / קישורים\nאפיון: {SPEC} S-1.1\n\n"
        f"### Plan\n- **אפיון:** {SPEC} S-9.9\n"
    )
    assert spec_check.issue_spec(issue(5, body)) == (SPEC, ["S-1.1"])


def test_backlog_issue_needs_no_spec_line():
    assert spec_check.issue_gaps(SPECS, issue(5, "", "status:backlog")) == []


def test_open_part_without_an_issue_warns():
    found = spec_check.gaps(SPECS, [])
    assert [(gap.path, gap.line) for gap in found] == [(SPEC, 6)]
    assert "S-1.1 is open" in found[0].message


def test_pointed_part_is_no_gap():
    assert spec_check.gaps(SPECS, [pointing(5, "S-1.1")]) == []


def test_repo_without_specs_still_warns_on_issues():
    found = spec_check.gaps({}, [issue(5), issue(6, "", "status:backlog")])
    assert [gap.message[:3] for gap in found] == ["#5 "]


@pytest.mark.parametrize(
    "issues, expected",
    [
        (
            [pointing(5, "S-1.1", "status:in-progress")],
            "| S-1.1 | Read the spec | בעבודה | #5 |",
        ),
        (
            [pointing(5, "S-1.1", "status:explore")],
            "| S-1.1 | Read the spec | לא התחיל | #5 |",
        ),
        ([], "| S-1.1 | Read the spec | אין issue |  |"),
        (None, "| S-1.1 | Read the spec | לא נבדק |  |"),
    ],
)
def test_table_open_part(issues, expected):
    assert expected in spec_check.table(SPECS, issues).splitlines()


def test_table_done_and_out_of_scope():
    rows = spec_check.table(SPECS, []).splitlines()
    assert rows[0] == f"### {SPEC}"
    assert "| S-1.2 | Write the table | Done | #12 |" in rows
    assert "| S-1.3 | Old idea | מחוץ להיקף |  |" in rows


def test_gaps_never_change_the_exit_code(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    (folder / "pipeline.md").write_text(VALID, encoding="utf-8")
    monkeypatch.setattr(spec_check, "fetch_issues", lambda repo: [issue(5)])
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert spec_check.main(["--root", str(tmp_path), "--repo", "o/r"]) == 0
    out = capsys.readouterr().out
    assert "warning: #5 has no spec line" in out
    assert "0 errors, 2 warnings" in out


def test_unread_issues_only_warn(tmp_path, monkeypatch, capsys):
    def fail(repo):
        sys.exit("gh api failed")

    monkeypatch.setattr(spec_check, "fetch_issues", fail)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert spec_check.main(["--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "::warning::issues not read: gh api failed" in out
    assert "no spec files in docs/specs/ yet" in out


def test_error_is_an_annotation_in_actions(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    (folder / "x.md").write_text("## S-2 · broken\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert spec_check.main(["--root", str(tmp_path), "--no-issues"]) == 1
    assert "::error file=docs/specs/x.md,line=1::" in capsys.readouterr().out


@pytest.mark.parametrize(
    "text, code",
    [(VALID, 0), ("## S-1.1 · a\n## S-1.1 · b\n", 1)],
)
def test_run(tmp_path, text, code):
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    (folder / "pipeline.md").write_text(text, encoding="utf-8")
    done = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(tmp_path),
            "--no-issues",
            "--table",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert done.returncode == code
    assert "| מזהה | שם | מצב | issue |" in done.stdout


def test_duplicate_part_is_listed_once():
    parts, _ = spec_check.parse_spec("## S-1.1 · a\n\n## S-1.1 · b\n")
    assert [part.name for part in parts] == ["a"]


@pytest.mark.parametrize(
    "line",
    ["**מצב**: Done (#3)", "**Status** done", "**מצב:** Done #3"],
)
def test_near_status_line_is_an_error(line):
    parts, errors = spec_check.parse_spec(f"## S-1.1 · a\n{line}\n")
    assert [part.status for part in parts] == [None]
    assert len(errors) == 1
    assert errors[0][0] == 2
    assert "unknown status line" in errors[0][1]


def test_plain_first_line_is_no_status():
    parts, errors = spec_check.parse_spec("## S-1.1 · a\nStatus of the world.\n")
    assert errors == []
    assert parts[0].status is None


def test_multi_line_warning_stays_one_annotation(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    spec_check.emit("warning", spec_check.Finding(None, None, "a\nb 100%"))
    assert capsys.readouterr().out == "::warning::a%0Ab 100%25\n"


def test_annotation_has_no_second_place(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    spec_check.emit("error", spec_check.Finding(SPEC, 3, "bad"))
    assert capsys.readouterr().out == f"::error file={SPEC},line=3::bad\n"


def run_git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    """A git repo: the tag `before` has no docs/specs/, HEAD has two files there."""
    run_git(tmp_path, "init", "-q")
    run_git(tmp_path, "config", "user.email", "test@example.com")
    run_git(tmp_path, "config", "user.name", "test")
    run_git(tmp_path, "commit", "-q", "--allow-empty", "-m", "empty")
    run_git(tmp_path, "tag", "before")
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("## S-1 broken on purpose\n", encoding="utf-8")
    (folder / "pipeline.md").write_text(VALID, encoding="utf-8")
    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-q", "-m", "specs")
    return tmp_path


def test_spec_files_at_reads_the_ref_and_skips_readme(repo):
    assert spec_check.spec_files_at(repo, "HEAD") == {SPEC: VALID}


def test_spec_files_at_ref_without_specs_folder(repo):
    assert spec_check.spec_files_at(repo, "before") == {}


def test_spec_files_at_ignores_the_disk(repo):
    folder = repo / "docs" / "specs"
    (folder / "pipeline.md").write_text("# changed on disk\n", encoding="utf-8")
    (folder / "new.md").write_text("## S-9.1 · disk only\n", encoding="utf-8")
    assert spec_check.spec_files_at(repo, "HEAD") == {SPEC: VALID}


def test_spec_files_at_unknown_ref_is_an_error(repo):
    with pytest.raises(ValueError, match="no-such-ref"):
        spec_check.spec_files_at(repo, "no-such-ref")


def test_spec_files_at_reads_a_non_ascii_name(repo):
    (repo / "docs" / "specs" / "אפיון.md").write_text(VALID, encoding="utf-8")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "hebrew name")
    assert "docs/specs/אפיון.md" in spec_check.spec_files_at(repo, "HEAD")


@pytest.mark.parametrize(
    "ref, expected", [("HEAD", "1 spec files"), ("before", "no spec")]
)
def test_main_ref_reads_the_specs_of_the_ref(repo, ref, expected, capsys):
    (repo / "docs" / "specs" / "pipeline.md").unlink()
    code = spec_check.main(["--root", str(repo), "--no-issues", "--ref", ref])
    assert code == 0
    assert expected in capsys.readouterr().out


def test_main_unknown_ref_exits_with_the_reason(repo):
    with pytest.raises(SystemExit, match="spec files not read"):
        spec_check.main(["--root", str(repo), "--no-issues", "--ref", "nope"])
