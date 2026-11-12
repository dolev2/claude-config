"""spec_toc.py: the table of contents a spec file gets, and when it is stale."""

import pytest
import spec_check
import spec_toc

REPO = "o/r"

SPEC = """# Pipeline

Opening line.

## Stage one

### S-1.1 · Read the spec
**מצב:** פתוח (#5)

### S-1.2 · `/compact` after a merge
**מצב:** Done (#6)

```markdown
## S-9.9 · an example inside a code block is no heading
```

## Stage one
"""


def test_write_puts_the_block_before_the_first_heading():
    lines = spec_toc.write(SPEC, REPO).splitlines()
    start = lines.index(spec_toc.START)
    assert lines[start - 2] == "Opening line."
    assert lines[start + 1] == spec_toc.TITLE
    assert lines[lines.index(spec_toc.END) + 2] == "## Stage one"


def test_entries_nest_by_level_and_put_the_part_name_first():
    lines = spec_toc.build(SPEC)
    assert "- [Stage one](#stage-one)" in lines
    assert "  - [Read the spec (S-1.1)](#s-11--read-the-spec)" in lines
    assert (
        "  - [`/compact` after a merge (S-1.2)](#s-12--compact-after-a-merge)" in lines
    )
    assert not any("S-9.9" in line for line in lines)


def test_a_repeated_heading_gets_the_next_github_anchor():
    assert "- [Stage one](#stage-one-1)" in spec_toc.build(SPEC)


def test_write_twice_changes_nothing():
    once = spec_toc.write(SPEC, REPO)
    assert spec_toc.write(once, REPO) == once
    assert spec_toc.check(once, REPO) is None


def test_a_missing_block_warns_and_a_stale_one_fails():
    assert spec_toc.check(SPEC, REPO)[0] == 0
    stale = spec_toc.write(SPEC, REPO).replace(
        "### S-1.1 · Read the spec", "### S-1.1 · New"
    )
    line, message = spec_toc.check(stale, REPO)
    assert line > 0 and "stale" in message


def test_main_toc_writes_the_files_and_then_the_check_passes(tmp_path, capsys):
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    (folder / "pipeline.md").write_text(SPEC, encoding="utf-8")
    assert spec_check.main(["--root", str(tmp_path), "--repo", REPO, "--toc"]) == 0
    assert "table of contents written" in capsys.readouterr().out
    assert (
        spec_check.main(["--root", str(tmp_path), "--repo", REPO, "--no-issues"]) == 0
    )
    assert "0 errors, 0 warnings" in capsys.readouterr().out


def test_main_fails_on_a_stale_block(tmp_path, capsys):
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    stale = spec_toc.write(SPEC, REPO).replace(
        "## Stage one\n\n###", "## Renamed\n\n###", 1
    )
    (folder / "pipeline.md").write_text(stale, encoding="utf-8")
    assert (
        spec_check.main(["--root", str(tmp_path), "--repo", REPO, "--no-issues"]) == 1
    )
    assert "table of contents is stale" in capsys.readouterr().out


def test_part_anchors_name_each_part_by_its_id():
    assert spec_toc.part_anchors(SPEC) == {
        "S-1.1": "s-11--read-the-spec",
        "S-1.2": "s-12--compact-after-a-merge",
    }


STATUSES = """# Pipeline

## Stage one

### Group
#### S-1.1 · Done part
**מצב:** Done (#226)

#### S-1.2 · Open part
**מצב:** פתוח (#280, #281)

#### S-1.3 · No status
Text.

#### S-1.4 · Out
**מצב:** מחוץ להיקף
"""
URL = "https://github.com/o/r/issues/"


def test_each_part_shows_its_status_and_issue_links():
    lines = spec_toc.build(STATUSES, REPO)
    assert (
        f"    - [Done part (S-1.1)](#s-11--done-part) · גמור: [#226]({URL}226)" in lines
    )
    assert (
        f"    - [Open part (S-1.2)](#s-12--open-part) · פתוח: [#280]({URL}280), "
        f"[#281]({URL}281)"
    ) in lines


@pytest.mark.parametrize(
    "entry",
    [
        "- [Stage one](#stage-one)",
        "  - [Group](#group)",
        "    - [No status (S-1.3)](#s-13--no-status)",
        "    - [Out (S-1.4)](#s-14--out)",
    ],
)
def test_no_status_out_of_scope_chapter_and_group_add_nothing(entry):
    assert entry in spec_toc.build(STATUSES, REPO)


def test_a_status_change_without_toc_fails():
    written = spec_toc.write(STATUSES, REPO)
    changed = written.replace("**מצב:** פתוח (#280, #281)", "**מצב:** Done (#281)")
    line, message = spec_toc.check(changed, REPO)
    assert line > 0 and "stale" in message


def test_the_older_form_that_matches_the_headings_only_warns():
    lines = spec_toc.write(STATUSES, REPO).splitlines()
    start, end = spec_toc.region(lines)
    lines[start : end + 1] = spec_toc.build(STATUSES)
    older = "\n".join(lines) + "\n"
    assert spec_toc.check(older, REPO) == (
        0,
        "the table of contents has no status: run spec_check.py --toc",
    )
    renamed = older.replace("#### S-1.3 · No status", "#### S-1.3 · Renamed")
    line, message = spec_toc.check(renamed, REPO)
    assert line > 0 and "stale" in message


def test_write_twice_with_statuses_changes_nothing():
    once = spec_toc.write(STATUSES, REPO)
    assert spec_toc.write(once, REPO) == once
    assert spec_toc.check(once, REPO) is None
