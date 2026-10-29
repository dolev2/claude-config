"""ps1_bom.py: a .ps1 without a BOM gets one, everything else is left alone."""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "ps1_bom.py"
spec = importlib.util.spec_from_file_location("ps1_bom", SCRIPT)
ps1_bom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ps1_bom)

BOM = b"\xef\xbb\xbf"
HEBREW_SCRIPT = "Write-Host 'שלום'\r\n".encode()


class FakeStream:
    """A stdin stand-in with the `.buffer` the hook reads."""

    def __init__(self, data: bytes = b"") -> None:
        self.buffer = io.BytesIO(data)


def run_hook(monkeypatch, raw: str) -> int:
    """Run main() on raw stdin text; return its exit code."""
    monkeypatch.setattr(sys, "stdin", FakeStream(raw.encode("utf-8")))
    return ps1_bom.main()


def tool_call(file_path: str, cwd: str = "", tool: str = "Write") -> str:
    """The JSON Claude Code sends for an edit tool call."""
    return json.dumps(
        {"tool_name": tool, "cwd": cwd, "tool_input": {"file_path": file_path}}
    )


def test_adds_bom_and_keeps_content(tmp_path, monkeypatch):
    script = tmp_path / "run.ps1"
    script.write_bytes(HEBREW_SCRIPT)
    assert run_hook(monkeypatch, tool_call(str(script))) == 0
    assert script.read_bytes() == BOM + HEBREW_SCRIPT


def test_second_run_does_not_add_another_bom(tmp_path, monkeypatch):
    script = tmp_path / "run.ps1"
    script.write_bytes(HEBREW_SCRIPT)
    run_hook(monkeypatch, tool_call(str(script), tool="Edit"))
    run_hook(monkeypatch, tool_call(str(script), tool="Edit"))
    assert script.read_bytes() == BOM + HEBREW_SCRIPT


def test_relative_path_resolves_against_cwd(tmp_path, monkeypatch):
    script = tmp_path / "run.ps1"
    script.write_bytes(HEBREW_SCRIPT)
    run_hook(monkeypatch, tool_call("run.ps1", cwd=str(tmp_path)))
    assert script.read_bytes().startswith(BOM)


def test_upper_case_extension(tmp_path):
    script = tmp_path / "RUN.PS1"
    script.write_bytes(HEBREW_SCRIPT)
    assert ps1_bom.add_bom(script)
    assert script.read_bytes().startswith(BOM)


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("tool.py", HEBREW_SCRIPT),
        ("utf16.ps1", b"\xff\xfe" + "שלום".encode("utf-16-le")),
        ("utf16be.ps1", b"\xfe\xff" + "שלום".encode("utf-16-be")),
    ],
)
def test_leaves_file_alone(tmp_path, name, content):
    target = tmp_path / name
    target.write_bytes(content)
    assert not ps1_bom.add_bom(target)
    assert target.read_bytes() == content


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        json.dumps({"tool_name": "Write", "tool_input": {}}),
        tool_call("/no/such/folder/run.ps1"),
    ],
)
def test_bad_input_exits_zero(monkeypatch, raw):
    assert run_hook(monkeypatch, raw) == 0
