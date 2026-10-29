"""ruff_on_edit.py: a .py file under ruff settings is formatted, lint goes to Claude."""

import importlib.util
import io
import json
import shutil
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "ruff_on_edit.py"
spec = importlib.util.spec_from_file_location("ruff_on_edit", SCRIPT)
ruff_on_edit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ruff_on_edit)

needs_ruff = pytest.mark.skipif(not shutil.which("ruff"), reason="ruff not installed")

BROKEN_FORMAT = "x  =  [1,2 ,3]\n"
FORMATTED = "x = [1, 2, 3]\n"
UNUSED_IMPORT = "import os\n\nx  =  1\n"


class FakeStream:
    """A stdin stand-in with the `.buffer` the hook reads."""

    def __init__(self, data: bytes = b"") -> None:
        self.buffer = io.BytesIO(data)


def run_hook(monkeypatch, raw: str) -> tuple[int, str]:
    """Run main() on raw stdin text; return its exit code and its stdout."""
    stdout = FakeStream()
    monkeypatch.setattr(sys, "stdin", FakeStream(raw.encode("utf-8")))
    monkeypatch.setattr(sys, "stdout", stdout)
    code = ruff_on_edit.main()
    return code, stdout.buffer.getvalue().decode("utf-8")


def tool_call(file_path: str, tool: str = "Edit") -> str:
    """The JSON Claude Code sends for an edit tool call."""
    return json.dumps({"tool_name": tool, "tool_input": {"file_path": file_path}})


def make_repo(root: Path, config: str = "ruff.toml", content: str = "") -> Path:
    """A folder that looks like a git repo, with the given ruff settings file."""
    (root / ".git").mkdir()
    (root / config).write_text(content, encoding="utf-8")
    return root


@needs_ruff
def test_formats_file_under_ruff_toml(tmp_path, monkeypatch):
    make_repo(tmp_path)
    source = tmp_path / "pkg" / "module.py"
    source.parent.mkdir()
    source.write_text(BROKEN_FORMAT, encoding="utf-8")
    code, output = run_hook(monkeypatch, tool_call(str(source)))
    assert code == 0
    assert source.read_text(encoding="utf-8") == FORMATTED
    assert output == ""


@needs_ruff
def test_pyproject_with_ruff_section_counts(tmp_path, monkeypatch):
    make_repo(tmp_path, "pyproject.toml", "[tool.ruff]\nline-length = 88\n")
    source = tmp_path / "module.py"
    source.write_text(BROKEN_FORMAT, encoding="utf-8")
    run_hook(monkeypatch, tool_call(str(source), tool="Write"))
    assert source.read_text(encoding="utf-8") == FORMATTED


@needs_ruff
def test_lint_left_goes_to_claude_without_fix(tmp_path, monkeypatch):
    make_repo(tmp_path, content='lint.select = ["F"]\n')
    source = tmp_path / "module.py"
    source.write_text(UNUSED_IMPORT, encoding="utf-8")
    code, output = run_hook(monkeypatch, tool_call(str(source)))
    assert code == 0
    assert source.read_text(encoding="utf-8") == "import os\n\nx = 1\n"
    feedback = json.loads(output)["hookSpecificOutput"]
    assert feedback["hookEventName"] == "PostToolUse"
    assert "F401" in feedback["additionalContext"]


@pytest.mark.parametrize(
    "config", ["", "pyproject.toml without ruff", "ruff.toml above the git root"]
)
def test_no_ruff_settings_leaves_file_alone(tmp_path, monkeypatch, config):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    if config == "pyproject.toml without ruff":
        (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    elif config == "ruff.toml above the git root":
        (tmp_path / "ruff.toml").write_text("")
    source = repo / "module.py"
    source.write_text(BROKEN_FORMAT, encoding="utf-8")
    assert run_hook(monkeypatch, tool_call(str(source))) == (0, "")
    assert source.read_text(encoding="utf-8") == BROKEN_FORMAT


def test_no_ruff_on_path_leaves_file_alone(tmp_path, monkeypatch):
    make_repo(tmp_path)
    source = tmp_path / "module.py"
    source.write_text(BROKEN_FORMAT, encoding="utf-8")
    monkeypatch.setattr(ruff_on_edit.shutil, "which", lambda _name: None)
    assert run_hook(monkeypatch, tool_call(str(source))) == (0, "")
    assert source.read_text(encoding="utf-8") == BROKEN_FORMAT


def test_ruff_that_fails_to_run_leaves_file_alone(tmp_path, monkeypatch):
    make_repo(tmp_path)
    source = tmp_path / "module.py"
    source.write_text(BROKEN_FORMAT, encoding="utf-8")
    missing = str(tmp_path / "no-such-ruff")
    monkeypatch.setattr(ruff_on_edit.shutil, "which", lambda _name: missing)
    assert run_hook(monkeypatch, tool_call(str(source))) == (0, "")
    assert source.read_text(encoding="utf-8") == BROKEN_FORMAT


def test_other_files_left_alone(tmp_path, monkeypatch):
    make_repo(tmp_path)
    notes = tmp_path / "notes.txt"
    notes.write_text(BROKEN_FORMAT, encoding="utf-8")
    assert run_hook(monkeypatch, tool_call(str(notes))) == (0, "")
    assert notes.read_text(encoding="utf-8") == BROKEN_FORMAT


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        json.dumps({"tool_name": "Edit", "tool_input": {}}),
        tool_call("/no/such/folder/module.py"),
    ],
)
def test_bad_input_exits_zero(monkeypatch, raw):
    assert run_hook(monkeypatch, raw) == (0, "")
