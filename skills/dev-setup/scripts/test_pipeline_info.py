"""pipeline_info.py: where the issue forms are read from, and what counts as missing."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "pipeline_info.py"
spec = importlib.util.spec_from_file_location("pipeline_info", SCRIPT)
pipeline_info = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline_info)


def fake_gh(monkeypatch, *, defaults=True, root=None):
    """Answer the gh/git calls main() makes; record the paths asked of the contents API."""
    asked = []

    def run(*args):
        if args[:2] == ("git", "rev-parse"):
            return (0, str(root)) if root else (1, "")
        if args[:3] == ("gh", "repo", "view"):
            return 0, json.dumps({"nameWithOwner": "acme/widgets", "defaultBranchRef": {"name": "main"}})
        if args[:3] == ("gh", "label", "list"):
            return 0, "\n".join(pipeline_info.REQUIRED_LABELS + ["owner:dana"])
        if args[:2] == ("gh", "api") and "/contents/" in args[2]:
            asked.append(args[2])
            return (0, ".github/ISSUE_TEMPLATE/task.yml") if defaults else (1, "")
        return 1, ""

    monkeypatch.setattr(pipeline_info, "run", run)
    return asked


def write_forms(root):
    for f in pipeline_info.FORM_FILES:
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text("name: x\n", encoding="utf-8")


def test_local_forms_win(monkeypatch, tmp_path):
    write_forms(tmp_path)
    asked = fake_gh(monkeypatch)
    assert pipeline_info.issue_forms(tmp_path, "acme/widgets") == "repo"
    assert asked == []


def test_one_local_form_is_not_enough(monkeypatch, tmp_path):
    write_forms(tmp_path)
    (tmp_path / pipeline_info.FORM_FILES[1]).unlink()
    fake_gh(monkeypatch)
    assert pipeline_info.issue_forms(tmp_path, "acme/widgets") == "acme/.github"


def test_defaults_come_from_the_repo_owner(monkeypatch, tmp_path):
    asked = fake_gh(monkeypatch)
    assert pipeline_info.issue_forms(tmp_path, "acme/widgets") == "acme/.github"
    assert asked == ["repos/acme/.github/contents/.github/ISSUE_TEMPLATE/task.yml"]


def test_no_forms_anywhere(monkeypatch, tmp_path):
    fake_gh(monkeypatch, defaults=False)
    assert pipeline_info.issue_forms(tmp_path, "acme/widgets") is None


def run_main(monkeypatch, capsys, argv=("--json",)):
    pipeline_info.main(list(argv))
    return json.loads(capsys.readouterr().out)


def test_default_forms_are_not_missing(monkeypatch, capsys, tmp_path):
    fake_gh(monkeypatch, root=tmp_path)
    info = run_main(monkeypatch, capsys)
    assert info["issue_forms"] == "acme/.github"
    assert not any("ISSUE_TEMPLATE" in f for f in info["missing_files"])


def test_missing_forms_are_reported(monkeypatch, capsys, tmp_path):
    fake_gh(monkeypatch, defaults=False, root=tmp_path)
    info = run_main(monkeypatch, capsys)
    assert info["issue_forms"] is None
    assert info["missing_files"][0] == ".github/ISSUE_TEMPLATE (repo or acme/.github)"


def test_missing_forms_are_reported_for_a_remote_repo(monkeypatch, capsys):
    fake_gh(monkeypatch, defaults=False)
    info = run_main(monkeypatch, capsys, ("--json", "--repo", "acme/widgets"))
    assert info["missing_files"] == [".github/ISSUE_TEMPLATE (repo or acme/.github)"]


def write_readme(root, text):
    (root / "README.md").write_text(text, encoding="utf-8")


def test_no_readme_is_no_file_guide(tmp_path):
    assert not pipeline_info.has_file_guide(tmp_path)


def test_readme_without_the_heading_is_no_file_guide(tmp_path):
    write_readme(tmp_path, "# widgets\n\nSee the file guide below, and the מדריך קבצים too.\n")
    assert not pipeline_info.has_file_guide(tmp_path)


def test_file_guide_heading_in_hebrew_or_english_at_any_level(tmp_path):
    for heading in ("## מדריך קבצים", "# File guide", "### file Guide: root", "#### מדריך קבצים לריפו"):
        write_readme(tmp_path, f"# widgets\n\n{heading}\n| a | b |\n")
        assert pipeline_info.has_file_guide(tmp_path), heading


def test_missing_file_guide_is_reported(monkeypatch, capsys, tmp_path):
    fake_gh(monkeypatch, root=tmp_path)
    info = run_main(monkeypatch, capsys)
    assert "README.md (file guide)" in info["missing_files"]


def test_present_file_guide_is_not_reported(monkeypatch, capsys, tmp_path):
    write_readme(tmp_path, "# widgets\n\n## מדריך קבצים\n")
    fake_gh(monkeypatch, root=tmp_path)
    info = run_main(monkeypatch, capsys)
    assert not any("file guide" in f for f in info["missing_files"])
