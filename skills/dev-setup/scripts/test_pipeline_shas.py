"""pipeline_shas.py: the two shas that tell the orchestrator its pipeline changed."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pipeline_shas  # noqa: E402


def sh(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def cache(tmp_path):
    return tmp_path / "cache.git"


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    """A local git repo standing in for the pipeline's remote; commit(path) adds one."""
    remote = tmp_path / "remote"
    remote.mkdir()
    sh(remote, "init", "-q", "-b", "main")
    sh(remote, "config", "user.email", "t@example.com")
    sh(remote, "config", "user.name", "t")
    # file://, so the cache is a real blob-less clone, as from GitHub; a plain path
    # makes git ignore --filter.
    monkeypatch.setattr(pipeline_shas, "PIPELINE_URL", remote.as_uri())

    def commit(path):
        file = remote / path
        if not file.suffix:
            file.mkdir(exist_ok=True)
            file = file / "f.md"
        file.write_text(file.read_text() + "x" if file.exists() else "x")
        sh(remote, "add", "-A")
        sh(remote, "commit", "-q", "-m", path)
        out = subprocess.run(
            ["git", "-C", str(remote), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return out.stdout.strip()

    return commit


def shas(cache):
    result = pipeline_shas.pipeline_shas(cache)
    return result["pipeline_sha"], result["session_sha"]


@pytest.mark.parametrize(
    ("changed", "group"),
    [("rules", 1), ("settings.json", 1), ("skills", 0), ("hooks", 0)],
)
def test_a_merge_moves_only_the_sha_of_its_group(pipeline, cache, changed, group):
    first = [pipeline("skills"), pipeline("CLAUDE.md")]
    assert list(shas(cache)) == first

    new = pipeline(changed)
    second = list(shas(cache))
    assert second[group] == new
    assert second[1 - group] == first[1 - group]


def test_a_merge_outside_both_groups_moves_neither(pipeline, cache):
    """A one-commit clone would name this commit for both: the trap of ~/.claude."""
    first = [pipeline("skills"), pipeline("rules")]
    pipeline("README.md")
    assert list(shas(cache)) == first


def test_a_group_without_commits_is_null(pipeline, cache):
    sha = pipeline("hooks")
    assert shas(cache) == (sha, None)


def test_a_failing_fetch_on_an_existing_cache_leaves_null_shas(
    pipeline, cache, tmp_path, capsys
):
    pipeline("skills")
    shas(cache)
    shutil.rmtree(tmp_path / "remote")
    result = pipeline_shas.pipeline_shas(cache)
    out = capsys.readouterr()
    assert result["pipeline_sha"] is None and result["session_sha"] is None
    assert "pipeline-change check did not run" in out.err


def test_a_broken_cache_is_cloned_again(pipeline, cache):
    sha = pipeline("skills")
    cache.mkdir()
    (cache / "junk").write_text("x")
    assert shas(cache) == (sha, None)
