"""Run the skill evals: fixed scenarios that catch a SKILL.md change breaking a rule.

Builds a temporary plugin (a copy of skills/, a plugin.json and the cases), puts the
fake gh first on PATH, and runs `claude plugin eval` on it. Which cases run follows the
files changed against origin/main: a covered skill runs its own tag, and a change in
skills/dev-setup/reference/ or in evals/ runs them all. Linux and cloud only: Bash in a
case needs the sandbox (bubblewrap and socat).
The decision: docs/decisions/183-skill-evals.md.

Exit codes: 0 every case passed (or nothing to run), 1 a case failed, 2 not run
(missing tools, a work folder the sandbox cannot reach) or stopped at the cost ceiling.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from summary import summarize

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
SKILLS = ("dev-ship", "dev-code", "dev-plan")
RUN_ALL = ("skills/dev-setup/reference/", "evals/")
TOOLS = ("claude", "bwrap", "socat", "jq", "git")
HOME_COPY = ("CLAUDE.md", "rules", "skills", "docs")
PLUGIN_NAME = "skill-evals"
DEFAULT_CEILING_USD = 10.0
RUNS = 2


def changed_files(base: str) -> list[str]:
    """Files changed against base, committed or not."""
    committed = subprocess.run(
        ["git", "-C", str(ROOT), "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    status = subprocess.run(
        ["git", "-C", str(ROOT), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    return sorted(set(committed) | {line[3:].strip() for line in status if line})


def tags_for(files: list[str]) -> list[str]:
    """The skill tags to run for these changed files; empty means nothing to run."""
    if any(f.startswith(RUN_ALL) for f in files):
        return list(SKILLS)
    return [s for s in SKILLS if any(f.startswith(f"skills/{s}/") for f in files)]


def missing_tools() -> list[str]:
    """What the run needs that is not on PATH."""
    return [tool for tool in TOOLS if not shutil.which(tool)]


def unreachable(folder: Path) -> str | None:
    """Why the sandbox cannot use a work folder here, or None.

    The sandbox denies writes under /tmp and every read under the real HOME, and the
    run's temporary home lives under TMPDIR, so the work folder must be outside both.
    """
    resolved = folder.resolve()
    home = Path.home().resolve()
    for blocked in (Path("/tmp"), Path("/var/tmp"), home):
        if resolved == blocked or blocked in resolved.parents:
            return f"{resolved} is under {blocked}, which the eval sandbox blocks"
    return None


def build_plugin(work: Path, holdout: bool) -> Path:
    """The temporary plugin: skills, plugin.json, the cases, and a ~/.claude copy.

    One level below work: the sandbox denies reads in the plugin's parent folder, and
    the fake gh in work/fake must stay readable.
    """
    plugin = work / "plugin" / PLUGIN_NAME
    shutil.copytree(ROOT / "skills", plugin / "skills")
    manifest = plugin / ".claude-plugin" / "plugin.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"name": PLUGIN_NAME, "version": "0.0.0", "description": "evals"}),
        encoding="utf-8",
    )
    cases = EVALS / ("holdout" if holdout else "cases")
    shutil.copytree(cases, plugin / "evals")
    shutil.copy(EVALS / "scaffold.sh", plugin / "evals" / "scaffold.sh")
    shutil.copytree(EVALS / "fixture", plugin / "evals" / "fixture")
    for name in HOME_COPY:
        source = ROOT / name
        target = plugin / "claude-home" / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, target)
    return plugin


def install_fake_gh(work: Path) -> Path:
    """The fake gh and its modules in work/fake; returns the folder to put on PATH."""
    fake = work / "fake"
    (fake / "bin").mkdir(parents=True)
    for name in (
        "fake_gh.py",
        "fake_gh_rest.py",
        "fake_gh_state.py",
        "fake_gh_graphql.py",
    ):
        shutil.copy(EVALS / name, fake / name)
    gh = fake / "bin" / "gh"
    shutil.copy(EVALS / "bin" / "gh", gh)
    gh.chmod(0o755)
    return fake / "bin"


def eval_command(plugin: Path, args: argparse.Namespace, tags: list[str]) -> list[str]:
    """The `claude plugin eval` command line."""
    command = [
        "claude",
        "plugin",
        "eval",
        str(plugin),
        "--ablation",
        "none",
        "--scaffold",
        "--trust-plugin",
        "--runs",
        str(RUNS),
        "--no-publish",
        "--keep-temp",
        "--max-cost-usd",
        str(args.max_cost_usd),
        "--json",
        str(plugin.parent.parent / "result.json"),
    ]
    if args.model:
        command += ["--model", args.model]
    command += ["--allow-tools", "Bash", "Write", "Edit"]
    if args.case:
        command += ["--case", args.case]
    if tags:
        command += ["--tag", *tags]
    return command


def eval_env(fake_bin: Path, work: Path) -> dict[str, str]:
    """The environment: fake gh first, TMPDIR outside /tmp, and not a cloud session.

    Without CLAUDE_CODE_REMOTE the skills use the plain gh forms, as on Dolev's machine.
    """
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_REMOTE", None)
    env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"
    # Short: the sandbox's sockets live under TMPDIR, and a socket path is capped at
    # about 100 characters.
    tmp = work.parent / "tmp"
    tmp.mkdir(exist_ok=True)
    env["TMPDIR"] = str(tmp)
    return env


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="every case, any diff")
    parser.add_argument("--holdout", action="store_true", help="the held-out set")
    parser.add_argument("--dry-run", action="store_true", help="print, do not run")
    parser.add_argument("--model", help="a model other than the session's")
    parser.add_argument("--case", help="only the cases whose name matches this glob")
    parser.add_argument(
        "--max-cost-usd", type=float, default=DEFAULT_CEILING_USD, help="cost ceiling"
    )
    parser.add_argument(
        "--base", default="origin/main", help="what the diff is against"
    )
    parser.add_argument(
        "--work-dir", type=Path, default=EVALS / "results", help="where runs go"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Pick the cases, run them, and print one line per skill."""
    args = parse_args(argv)
    tags = (
        list(SKILLS) if args.all or args.holdout else tags_for(changed_files(args.base))
    )
    if not tags:
        print("אין סקיל מכוסה בשינוי: התרחישים לא הורצו.")
        return 0
    missing = missing_tools()
    if missing:
        print(
            f"לא הורץ: חסר {', '.join(missing)} (apt-get install -y bubblewrap socat)."
        )
        return 2
    blocked = unreachable(args.work_dir)
    if blocked:
        print(f"לא הורץ: {blocked}. הריצו מ-clone מחוץ ל-HOME ול-/tmp.")
        return 2
    work = args.work_dir / time.strftime("run-%Y%m%d-%H%M%S")
    work.mkdir(parents=True)
    plugin = build_plugin(work, args.holdout)
    fake_bin = install_fake_gh(work)
    command = eval_command(plugin, args, [] if args.holdout else tags)
    if args.dry_run:
        print(" ".join(command))
        shutil.rmtree(work)
        return 0
    print(
        f"מריץ: {', '.join(tags)}{' (הסט השמור)' if args.holdout else ''}", flush=True
    )
    code = subprocess.run(command, env=eval_env(fake_bin, work), check=False).returncode
    result = plugin.parent.parent / "result.json"
    if not result.exists():
        print(f"לא הורץ: claude plugin eval יצא ב-{code} בלי תוצאה.")
        return 2
    lines, failed = summarize(json.loads(result.read_text(encoding="utf-8")), SKILLS)
    print("\n".join(lines))
    print(f"הדוח המלא: {result}")
    if code == 2:
        return 2
    return 1 if failed or code else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
