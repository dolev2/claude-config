"""The two shas that tell the sprint orchestrator its pipeline changed mid-sprint.

    pipeline_sha     the last commit on the pipeline's main that touched what is read
                     from disk on every use (RELOAD_PATHS)
    session_sha      the last commit on the pipeline's main that touched what a session
                     loads once, at its start (SESSION_PATHS)

Both shas are read with git, from a blob-less bare clone kept in CACHE, never from the
REST API: a cloud session reaches the API only of the repos attached to it, and an
orchestrator of a project repo has only its project (claude-config #211). Not from
~/.claude either: that is a one-commit clone, where `git log -- <path>` always names its
single commit. When git fails, both are null with a warning on stderr, and the rest of
the state is printed as usual. A cache git cannot use is deleted and cloned again once;
two runs racing on it only make one of them print nulls.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

PIPELINE_URL = "https://github.com/dolev2/claude-config"
CACHE = Path.home() / ".cache" / "claude-config-pipeline.git"
GIT_TIMEOUT_SECONDS = 60
# The two groups of the pipeline repo's paths (claude-config #192). A hook's script is
# read from disk on every run, so it reloads; registering a hook is a settings.json
# change, so it does not.
RELOAD_PATHS = ["skills", "hooks"]
SESSION_PATHS = ["CLAUDE.md", "rules", "settings.json"]


def git(*args: str) -> str:
    """Runs git without prompting for credentials; its stdout. Raises on failure."""
    env = os.environ | {"GIT_TERMINAL_PROMPT": "0"}
    done = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    return done.stdout


def refresh_cache(cache: Path) -> None:
    """Clones the pipeline repo into `cache` once, then brings its main up to date.

    Full history without blobs: `git log -- <path>` compares trees, never file contents.
    """
    if not (cache / "HEAD").exists():
        git("clone", "-q", "--bare", "--filter=blob:none", PIPELINE_URL, str(cache))
    git("-C", str(cache), "fetch", "-q", "origin", "+refs/heads/main:refs/heads/main")


def last_commit(cache: Path, paths: list[str]) -> str | None:
    """The newest commit on the cached main that touched any of `paths`, or None."""
    out = git("-C", str(cache), "log", "-1", "--format=%H", "main", "--", *paths)
    return out.strip() or None


def read_shas(cache: Path) -> dict:
    """Refreshes the cache and reads both shas from it. Raises when git fails."""
    refresh_cache(cache)
    return {
        "pipeline_sha": last_commit(cache, RELOAD_PATHS),
        "session_sha": last_commit(cache, SESSION_PATHS),
    }


def pipeline_shas(cache: Path) -> dict:
    """pipeline_sha and session_sha; both None, with a warning, when git fails.

    A cache git cannot use (half cloned, corrupt) would fail every later check, so on a
    failure it is deleted and cloned again, once.
    """
    try:
        try:
            return read_shas(cache)
        except subprocess.CalledProcessError:
            shutil.rmtree(cache, ignore_errors=True)
            return read_shas(cache)
    except (subprocess.SubprocessError, OSError) as err:
        detail = getattr(err, "stderr", None) or str(err)
        print(
            f"warning: pipeline shas not read, the pipeline-change check did not run: "
            f"{detail.strip()}",
            file=sys.stderr,
        )
        return {"pipeline_sha": None, "session_sha": None}
