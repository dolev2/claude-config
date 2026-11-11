"""spec_toc.py: the table of contents a spec file gets, and when it is stale."""

import spec_check
import spec_toc

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
    lines = spec_toc.write(SPEC).splitlines()
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
    once = spec_toc.write(SPEC)
    assert spec_toc.write(once) == once
    assert spec_toc.check(once) is None


def test_a_missing_block_warns_and_a_stale_one_fails():
    assert spec_toc.check(SPEC)[0] == 0
    stale = spec_toc.write(SPEC).replace("### S-1.1 · Read the spec", "### S-1.1 · New")
    line, message = spec_toc.check(stale)
    assert line > 0 and "stale" in message


def test_main_toc_writes_the_files_and_then_the_check_passes(tmp_path, capsys):
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    (folder / "pipeline.md").write_text(SPEC, encoding="utf-8")
    assert spec_check.main(["--root", str(tmp_path), "--toc"]) == 0
    assert "table of contents written" in capsys.readouterr().out
    assert spec_check.main(["--root", str(tmp_path), "--no-issues"]) == 0
    assert "0 errors, 0 warnings" in capsys.readouterr().out


def test_main_fails_on_a_stale_block(tmp_path, capsys):
    folder = tmp_path / "docs" / "specs"
    folder.mkdir(parents=True)
    stale = spec_toc.write(SPEC).replace("## Stage one\n\n###", "## Renamed\n\n###", 1)
    (folder / "pipeline.md").write_text(stale, encoding="utf-8")
    assert spec_check.main(["--root", str(tmp_path), "--no-issues"]) == 1
    assert "table of contents is stale" in capsys.readouterr().out


def test_part_anchors_name_each_part_by_its_id():
    assert spec_toc.part_anchors(SPEC) == {
        "S-1.1": "s-11--read-the-spec",
        "S-1.2": "s-12--compact-after-a-merge",
    }
