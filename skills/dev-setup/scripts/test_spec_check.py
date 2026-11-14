"""spec_check.py: the errors in a spec file, the gaps against the issues, the table."""

import subprocess
import sys
from pathlib import Path

import pytest
import spec_check
import spec_toc
from spec_check import Part

SCRIPT = Path(__file__).resolve().parent / "spec_check.py"
VALID = """# Pipeline

## Stage one
Free grouping, no part.

### S-1.1 · Read the spec
**מצב:** פתוח (#5)

### S-1.2 · Write the table
**מצב:** Done (#12)

### S-1.3 · Two tasks
**מצב:** פתוח (#7, #8)

```markdown
## S-1.1 · an example inside a code block is no part
```
"""
SPEC = "docs/specs/pipeline.md"
REPO = "o/r"


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
        Part("S-1.1", "Read the spec", 6, "open", open_issues=(5,)),
        Part("S-1.2", "Write the table", 9, "done", 12),
        Part("S-1.3", "Two tasks", 12, "open", open_issues=(7, 8)),
    ]


@pytest.mark.parametrize(
    "line, status, issues",
    [
        ("**מצב:** פתוח (#12)", "open", (12,)),
        ("**מצב:** פתוח (#12, #13)", "open", (12, 13)),
        ("**מצב:** פתוח (#12,#13)", "open", (12, 13)),
        ("**status:** open (#4)", "open", (4,)),
        ("**מצב:** מחוץ להיקף", "out", ()),
    ],
)
def test_status_lines(line, status, issues):
    parts, errors = spec_check.parse_spec(f"## S-1.1 · a\n{line}\n")
    assert errors == []
    assert (parts[0].status, parts[0].open_issues) == (status, issues)


@pytest.mark.parametrize(
    "line",
    ["**מצב:** פתוח #12", "**מצב:** פתוח ()", "**מצב:** פתוח", "**מצב:** פתוח (12)"],
)
def test_broken_open_line_is_an_error(line):
    parts, errors = spec_check.parse_spec(f"## S-1.1 · a\n{line}\n")
    assert [part.status for part in parts] == [None]
    assert len(errors) == 1
    assert "unknown status line" in errors[0][1]
    assert "פתוח (#<N>)" in errors[0][1]


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


ALL_POINTING = [pointing(5, "S-1.1"), pointing(7, "S-1.3"), pointing(8, "S-1.3")]


def test_open_part_without_an_issue_warns():
    specs = {SPEC: spec_check.parse_spec("## S-2.1 · a\nText.\n")[0]}
    found = spec_check.gaps(specs, [])
    assert [(gap.path, gap.line) for gap in found] == [(SPEC, 1)]
    assert found[0].message == "S-2.1 is open, and no open issue points at it"


def test_open_line_with_no_open_issue_warns_once_per_number():
    found = spec_check.gaps(SPECS, ALL_POINTING[1:])
    assert [(gap.path, gap.line) for gap in found] == [(SPEC, 6)]
    assert "S-1.1 names #5" in found[0].message
    assert "not an open issue" in found[0].message


def test_pointed_part_is_no_gap():
    assert spec_check.gaps(SPECS, ALL_POINTING) == []


def test_part_with_no_status_line_and_an_issue_is_no_gap():
    specs = {SPEC: spec_check.parse_spec("## S-2.1 · a\nText.\n")[0]}
    assert spec_check.gaps(specs, [pointing(5, "S-2.1")]) == []


@pytest.mark.parametrize(
    "issues, expected",
    [
        (
            [pointing(5, "S-1.1"), pointing(7, "S-1.3")],
            "S-1.3 names #8 in its status line: not an open issue",
        ),
        (
            [pointing(5, "S-1.1"), pointing(7, "S-1.3"), pointing(8, "S-1.1")],
            f"the spec line of #8 does not name {SPEC} S-1.3",
        ),
        (
            [
                pointing(5, "S-1.1"),
                pointing(7, "S-1.3"),
                issue(8, "### הקשר / קישורים\nאפיון: docs/specs/other.md S-1.3\n"),
            ],
            f"the spec line of #8 does not name {SPEC} S-1.3",
        ),
    ],
)
def test_open_line_names_one_issue_in_vain(issues, expected):
    found = [gap for gap in spec_check.gaps(SPECS, issues) if gap.path == SPEC]
    assert len(found) == 1
    assert (found[0].line, expected in found[0].message) == (12, True)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("## S-2.1 · a\nText.\n", "S-2.1 is open with no status line"),
        ("## S-2.1 · a\n**מצב:** מחוץ להיקף\n", "S-2.1 is marked out of scope"),
    ],
)
def test_part_warnings(text, expected):
    found = spec_check.part_warnings(SPEC, spec_check.parse_spec(text)[0])
    assert [(gap.path, gap.line) for gap in found] == [(SPEC, 1)]
    assert expected in found[0].message


def test_done_and_open_parts_need_no_warning():
    assert spec_check.part_warnings(SPEC, SPECS[SPEC]) == []


@pytest.mark.parametrize("count, warns", [(0, False), (1, False), (2, True)])
def test_files_warning(count, warns):
    found = spec_check.files_warning(count)
    assert bool(found) == warns
    if warns:
        assert found[0].message.startswith("2 spec files in docs/specs/: one spec")


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
    out = {SPEC: spec_check.parse_spec("## S-1.3 · Old\n**מצב:** מחוץ להיקף\n")[0]}
    rows = spec_check.table(SPECS, []).splitlines()
    assert rows[0] == f"### {SPEC}"
    assert "| S-1.2 | Write the table | Done | #12 |" in rows
    assert "| S-1.3 | Old | מחוץ להיקף |  |" in spec_check.table(out, []).splitlines()


def test_gaps_never_change_the_exit_code(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    (folder / "pipeline.md").write_text(spec_toc.write(VALID, REPO), encoding="utf-8")
    found = [issue(5), *ALL_POINTING[1:]]
    monkeypatch.setattr(spec_check, "fetch_issues", lambda repo: found)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert spec_check.main(["--root", str(tmp_path), "--repo", "o/r"]) == 0
    out = capsys.readouterr().out
    assert "warning: #5 has no spec line" in out
    assert "0 errors, 2 warnings" in out


def test_out_of_scope_and_many_files_only_warn(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    out = "# B\n\n## S-1.1 · a\n**מצב:** מחוץ להיקף\n"
    (folder / "a.md").write_text(spec_toc.write(VALID, REPO), encoding="utf-8")
    (folder / "b.md").write_text(spec_toc.write(out, REPO), encoding="utf-8")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert (
        spec_check.main(["--root", str(tmp_path), "--repo", REPO, "--no-issues"]) == 0
    )
    printed = capsys.readouterr().out
    assert "warning: 2 spec files in docs/specs/: one spec per repo" in printed
    assert "warning: docs/specs/b.md:" in printed
    assert "S-1.1 is marked out of scope: delete the part" in printed
    assert "0 errors, 2 warnings" in printed


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
    assert (
        spec_check.main(["--root", str(tmp_path), "--repo", REPO, "--no-issues"]) == 1
    )
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
            "--repo",
            REPO,
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
    args = ["--root", str(repo), "--repo", REPO, "--no-issues", "--ref", ref]
    code = spec_check.main(args)
    assert code == 0
    assert expected in capsys.readouterr().out


def test_main_unknown_ref_exits_with_the_reason(repo):
    with pytest.raises(SystemExit, match="spec files not read"):
        spec_check.main(["--root", str(repo), "--no-issues", "--ref", "nope"])


def test_toc_with_repo_writes_full_issue_links(tmp_path):
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    (folder / "pipeline.md").write_text(VALID, encoding="utf-8")
    assert spec_check.main(["--root", str(tmp_path), "--repo", "a/b", "--toc"]) == 0
    text = (folder / "pipeline.md").read_text(encoding="utf-8")
    assert "· גמור: [#12](https://github.com/a/b/issues/12)" in text


def test_toc_without_repo_takes_the_origin_of_root(repo, capsys):
    run_git(repo, "remote", "add", "origin", "https://github.com/own/name.git")
    assert spec_check.main(["--root", str(repo), "--toc"]) == 0
    text = (repo / "docs" / "specs" / "pipeline.md").read_text(encoding="utf-8")
    assert "· פתוח: [#5](https://github.com/own/name/issues/5)" in text
    assert spec_check.main(["--root", str(repo), "--no-issues"]) == 0
    assert "0 errors" in capsys.readouterr().out


@pytest.mark.parametrize("flag", ["--toc", "--no-issues"])
def test_no_repo_and_no_origin_exits_with_the_message(repo, flag):
    with pytest.raises(SystemExit) as stop:
        spec_check.main(["--root", str(repo), flag])
    assert stop.value.code == spec_check.gh_rest.NOT_A_REPO


CHAPTERED = """# Spec

## פרק 1 · Hooks
**בריפו:** `hooks/`

### S-1.1 · x
**מצב:** Done (#3)
"""


def run_script(root: Path, *extra: str) -> subprocess.CompletedProcess:
    """spec_check.py --no-issues on `root`, as CI runs it."""
    command = [sys.executable, str(SCRIPT), "--root", str(root), "--repo", REPO]
    return subprocess.run(
        [*command, "--no-issues", *extra],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@pytest.fixture
def chaptered(tmp_path):
    """A git repo with hooks/ and a spec whose chapter names it; toc written."""
    run_git(tmp_path, "init", "-q")
    run_git(tmp_path, "config", "user.email", "test@example.com")
    run_git(tmp_path, "config", "user.name", "test")
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks" / "a.py").write_text("", encoding="utf-8")
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    (folder / "pipeline.md").write_text(CHAPTERED, encoding="utf-8")
    assert spec_check.main(["--root", str(tmp_path), "--repo", REPO, "--toc"]) == 0
    run_git(tmp_path, "add", ".")
    run_git(tmp_path, "commit", "-q", "-m", "spec")
    return tmp_path


def test_renamed_folder_fails_the_check(chaptered):
    done = run_script(chaptered)
    assert done.returncode == 0, done.stdout
    assert "0 warnings" in done.stdout
    (chaptered / "hooks").rename(chaptered / "guards")
    done = run_script(chaptered)
    assert done.returncode == 1
    assert "`hooks/` is no folder" in done.stdout


def test_ref_reads_the_folders_of_the_ref(chaptered):
    run_git(chaptered, "mv", "hooks", "guards")
    run_git(chaptered, "commit", "-q", "-m", "rename")
    assert run_script(chaptered, "--ref", "HEAD~1").returncode == 0
    done = run_script(chaptered, "--ref", "HEAD")
    assert done.returncode == 1
    assert "`hooks/` is no folder" in done.stdout
