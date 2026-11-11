"""A stand-in for the gh CLI in skill evals: GitHub state read from a JSON file.

An eval case seeds `gh-state/state.json` in its workspace (the scaffold writes the path
to $HOME/.fake-gh-state). Every call is logged to `gh-state/calls.jsonl`, and after
every change each issue's labels, body and comments, and each PR's state, are written
to plain files the graders read. A command this fake does not know is logged with
"unsupported" and exits 1, so a case never passes on a call that was not simulated.

Covers what the pipeline skills run: `gh issue view/edit/comment/list`,
`gh pr view/list/create/checks/merge/edit/comment`, and the REST forms of
`skills/dev-setup/reference/cloud.md` through `gh api` (fake_gh_rest.py).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import fake_gh_rest
from fake_gh_state import GhError, State


def state_dir() -> Path:
    """The case's state folder, from the pointer file the scaffold wrote."""
    pointer = Path(os.environ.get("HOME", "")) / ".fake-gh-state"
    if "FAKE_GH_STATE" in os.environ:
        return Path(os.environ["FAKE_GH_STATE"])
    if not pointer.exists():
        raise GhError(f"fake gh: no state ({pointer} is missing)")
    return Path(pointer.read_text(encoding="utf-8").strip())


def take(args: list[str], flag: str, many: bool = False) -> str | list[str] | None:
    """Remove `flag value` (or every one with many=True) from args; return the value."""
    values = []
    while flag in args:
        i = args.index(flag)
        values.append(args[i + 1] if i + 1 < len(args) else "")
        del args[i : i + 2]
    for arg in list(args):
        if arg.startswith(flag + "="):
            values.append(arg.split("=", 1)[1])
            args.remove(arg)
    return values if many else (values[-1] if values else None)


def has(args: list[str], flag: str) -> bool:
    """Remove a bare flag from args; return whether it was there."""
    found = flag in args
    while flag in args:
        args.remove(flag)
    return found


def emit(value: object, jq: str | None = None) -> str:
    """The output gh prints: JSON, or jq's raw output when --jq is given."""
    text = json.dumps(value, ensure_ascii=False, indent=2)
    if not jq:
        return text + "\n"
    if not shutil.which("jq"):
        raise GhError("fake gh: --jq needs jq on PATH")
    p = subprocess.run(
        ["jq", "-r", jq], input=text, capture_output=True, text=True, check=False
    )
    if p.returncode:
        raise GhError(p.stderr.strip() or "jq failed")
    return p.stdout


def pick(full: dict, fields: str | None) -> dict:
    """Only the --json fields asked for, as gh does."""
    if not fields:
        return full
    return {f: full.get(f) for f in fields.split(",")}


def body_arg(args: list[str]) -> str | None:
    """The text of --body or --body-file (`-` reads stdin)."""
    body = take(args, "--body") or take(args, "-b")
    path = take(args, "--body-file") or take(args, "-F")
    if path == "-":
        return sys.stdin.read()
    if path:
        return Path(path).read_text(encoding="utf-8")
    return body


VALUE_FLAGS = {"--add-label", "--remove-label", "--body", "-b", "--body-file", "-F"}
VALUE_FLAGS |= {"--title", "-t", "--repo", "-R", "--json", "--jq", "-q", "--label"}
VALUE_FLAGS |= {"-l", "--milestone", "-m", "--base", "-B", "--head", "-H", "--state"}
VALUE_FLAGS |= {"-s", "--subject", "--match-head-commit", "--assignee", "-a"}


def positionals(args: list[str]) -> list[str]:
    """The arguments that are not a flag or a flag's value, in order."""
    found, skip = [], False
    for arg in args:
        if skip:
            skip = False
        elif arg in VALUE_FLAGS:
            skip = True
        elif not arg.startswith("-"):
            found.append(arg)
    return found


def number_arg(args: list[str], state: State, kind: str) -> int:
    """The issue or PR number from the first positional argument (or `#N`, a URL)."""
    positional = positionals(args)
    if not positional:
        if kind == "pr":
            return state.pr_for_branch(state.current_branch())
        raise GhError(f"fake gh: {kind} number missing")
    ref = positional[0].rstrip("/").split("/")[-1].lstrip("#")
    if ref.isdigit():
        return int(ref)
    if kind == "pr":
        return state.pr_for_branch(ref)
    raise GhError(f"fake gh: not a number: {positional[0]}")


def issue_command(sub: str, args: list[str], state: State) -> str:
    """gh issue view / edit / comment / list."""
    fields, jq = take(args, "--json"), take(args, "--jq") or take(args, "-q")
    if sub == "list":
        labels = take(args, "--label", many=True) or []
        milestone = take(args, "--milestone")
        wanted = (take(args, "--state") or "open").lower()
        rows = [
            pick(state.issue_cli(n), fields)
            for n in state.issue_numbers()
            if state.issue_matches(n, labels, milestone, wanted)
        ]
        return emit(rows, jq)
    number = number_arg(args, state, "issue")
    if sub == "view":
        full = state.issue_cli(number)
        if has(args, "--comments") and not fields:
            return "\n\n".join(c["body"] for c in full["comments"]) + "\n"
        return emit(pick(full, fields), jq)
    if sub == "edit":
        for label in take(args, "--add-label", many=True) or []:
            state.add_labels(number, label.split(","))
        for label in take(args, "--remove-label", many=True) or []:
            state.remove_labels(number, label.split(","))
        body = body_arg(args)
        if body is not None:
            state.set_body(number, body)
        return state.issue_url(number) + "\n"
    if sub == "comment":
        state.add_comment(number, body_arg(args) or "")
        return state.issue_url(number) + "#issuecomment\n"
    raise GhError(f"fake gh: unsupported: issue {sub}", unsupported=True)


def pr_command(sub: str, args: list[str], state: State) -> str:
    """gh pr view / list / create / checks / merge / edit / comment."""
    fields, jq = take(args, "--json"), take(args, "--jq") or take(args, "-q")
    if sub == "list":
        head = take(args, "--head")
        wanted = (take(args, "--state") or "open").lower()
        search = take(args, "--search")
        rows = [
            pick(state.pull_cli(n), fields)
            for n in state.pull_numbers()
            if state.pull_matches(n, head, wanted, search)
        ]
        return emit(rows, jq)
    if sub == "create":
        number = state.create_pull(
            title=take(args, "--title") or take(args, "-t") or "",
            body=body_arg(args) or "",
            head=take(args, "--head") or take(args, "-H") or state.current_branch(),
            base=take(args, "--base") or take(args, "-B") or state.default_branch,
        )
        return state.pull_url(number) + "\n"
    number = number_arg(args, state, "pr")
    if sub == "view":
        return emit(pick(state.pull_cli(number), fields), jq)
    if sub == "checks":
        conclusion = state.checks(number)
        line = f"tests\t{'pass' if conclusion == 'success' else 'fail'}\t1m\t\n"
        if conclusion != "success":
            raise GhError(line.strip(), output=line)
        return line
    if sub == "merge":
        state.merge(number)
        return f"✓ Squashed and merged pull request #{number}\n"
    if sub == "edit":
        state.edit_pull(number, take(args, "--title"), body_arg(args))
        return state.pull_url(number) + "\n"
    if sub == "comment":
        state.add_comment(number, body_arg(args) or "")
        return state.pull_url(number) + "#issuecomment\n"
    raise GhError(f"fake gh: unsupported: pr {sub}", unsupported=True)


def other_command(argv: list[str], state: State) -> str:
    """The few calls outside issue, pr and api that the scripts make."""
    if argv[:2] == ["variable", "get"]:
        raise GhError(f"variable {argv[2] if len(argv) > 2 else ''} was not found")
    if argv[:2] == ["repo", "view"]:
        args = argv[2:]
        fields, jq = take(args, "--json"), take(args, "--jq")
        full = {"nameWithOwner": state.repo, "visibility": "PRIVATE"}
        return emit(pick(full, fields), jq)
    if argv[:2] == ["auth", "status"]:
        return "✓ Logged in to github.com (fake)\n"
    raise GhError(f"fake gh: unsupported: {' '.join(argv)}", unsupported=True)


def run(argv: list[str], state: State) -> str:
    """Dispatch one gh command line; return what it prints."""
    if not argv:
        raise GhError("fake gh: no command", unsupported=True)
    head, rest = argv[0], list(argv[1:])
    if head == "api":
        jq = take(rest, "--jq") or take(rest, "-q")
        return emit(fake_gh_rest.handle(rest, state), jq)
    if head in ("issue", "pr") and rest:
        command = issue_command if head == "issue" else pr_command
        return command(rest[0], rest[1:], state)
    return other_command(argv, state)


def main(argv: list[str] | None = None) -> int:
    """Run one call, log it, and return gh's exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        folder = state_dir()
    except GhError as error:
        sys.stderr.write(error.message + "\n")
        return 1
    state = State.load(folder)
    entry: dict = {"argv": argv, "cwd": os.getcwd()}
    try:
        out = run(argv, state)
        entry["exit"] = 0
    except GhError as error:
        sys.stdout.write(error.output)
        sys.stderr.write(error.message + "\n")
        entry.update(exit=1, error=error.message, unsupported=error.unsupported)
        state.log(entry)
        return 1
    state.save()
    state.log(entry)
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
