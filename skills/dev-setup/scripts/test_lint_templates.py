"""templates/ruff.toml: clean code passes, and each code-python.md rule fails its case.

Runs the real ruff (pip install ruff==0.17.2, as CI does) on small files in a temporary
folder.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

CLEAN = """from fastapi import APIRouter, Depends, Query

router = APIRouter()


def current_user() -> str:
    return "dana"


@router.get("/deals")
def list_deals(user: str = Depends(current_user), limit: int = Query(10)) -> list[str]:
    return [user] * limit
"""


def ruff(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "ruff", *args, "--no-cache"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path):
    if ruff("--version", cwd=tmp_path).returncode != 0:
        pytest.fail("ruff is not installed: pip install ruff==0.17.2")
    shutil.copy(TEMPLATES / "ruff.toml", tmp_path / "ruff.toml")
    return tmp_path


def codes(repo: Path, source: str, name: str = "module.py") -> set[str]:
    """The rule codes ruff check reports for one file."""
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    result = ruff("check", "--output-format", "json", name, cwd=repo)
    return {finding["code"] for finding in json.loads(result.stdout)}


def test_clean_fastapi_route_passes(repo):
    assert codes(repo, CLEAN) == set()


def test_tests_need_no_type_hints(repo):
    assert (
        codes(repo, "def test_x(tmp_path):\n    assert tmp_path\n", "tests/test_x.py")
        == set()
    )


@pytest.mark.parametrize(
    ("source", "code"),
    [
        ("def f() -> None:\n    import os\n\n    print(os.sep)\n", "PLC0415"),
        (
            "def f() -> None:\n    try:\n        print(1)\n"
            "    except Exception:\n        pass\n",
            "BLE001",
        ),
        ("def f(x):\n    return x\n", "ANN001"),
        ("import os\n", "F401"),
        ("def BadName() -> None:\n    pass\n", "N802"),
        ("X = '" + "a" * 90 + "'\n", "E501"),
    ],
)
def test_each_rule_fails_its_violation(repo, source, code):
    assert code in codes(repo, source)


def test_format_check_fails_unformatted_code(repo):
    (repo / "module.py").write_text("x = {  'a':1 }\n", encoding="utf-8")
    assert ruff("format", "--check", "module.py", cwd=repo).returncode == 1


def test_local_block_is_honoured(repo):
    with (repo / "ruff.toml").open("a", encoding="utf-8") as f:
        f.write('lint.extend-per-file-ignores = { "module.py" = ["F401"] }\n')
    assert codes(repo, "import os\n") == set()


@pytest.mark.parametrize(
    ("template", "marker"),
    [("ruff.toml", "# --- local ---"), ("eslint.config.js", "// --- local ---")],
)
def test_one_local_marker_line(template, marker):
    lines = (TEMPLATES / template).read_text(encoding="utf-8").splitlines()
    assert [line.strip() for line in lines].count(marker) == 1
