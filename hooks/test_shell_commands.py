"""shell_commands.py: the commands a shell line runs, through wrappers and subshells."""

import shlex

import pytest
import shell_commands

INNER = ["git", "push", "-f"]


def commands(text: str) -> list[list[str]]:
    """Each subcommand of text, without its keywords, assignments and wrappers."""
    return [
        shell_commands.strip_prefixes(words)
        for words in shell_commands.split_subcommands(text)
    ]


@pytest.mark.parametrize(
    "text",
    [
        "(git push -f)",
        "{ git push -f; }",
        "if true; then git push -f; fi",
        "while true; do git push -f; done",
        "! git push -f",
        "y=$(git push -f)",
        'echo "$(git push -f)"',
        'echo "it\'s $(git push -f)"',
        "echo `git push -f`",
        "echo $(echo $(git push -f))",
        "sh -c 'git push -f'",
        'bash -c "git push -f"',
        "bash -lc 'git push -f'",
        "zsh -c 'git push -f'",
        "eval 'git push -f'",
        "eval git push -f",
        "env git push -f",
        "env -i -u HOME A=1 git push -f",
        "exec -a name git push -f",
        "echo x | xargs -I{} -n 1 git push -f",
        "nice -n 5 git push -f",
        "timeout 30 git push -f",
        "timeout -s KILL -k 5 30 git push -f",
        "sudo -u root -E git push -f",
        "stdbuf -oL git push -f",
        "time -p git push -f",
        "nohup git push -f",
        "/usr/bin/env git push -f",
        "GIT_TRACE=1 git push -f",
    ],
)
def test_inner_command_is_found(text):
    assert INNER in commands(text)


@pytest.mark.parametrize(
    "text",
    [
        "echo '$(git push -f)'",
        "echo 'a (git push -f) b'",
        'echo "a (git push -f) b"',
        'git commit -m "fix: git push -f"',
        "git commit -m \"$(cat <<'EOF'\nfix: git push -f\nEOF\n)\"",
        "cat > notes.md <<'EOF'\n(git push -f)\nEOF",
        "bash script.sh git push -f",
        "sh -c",
    ],
)
def test_text_is_not_a_command(text):
    assert INNER not in commands(text)


def wrapped(levels: int) -> str:
    """`git push -f` inside `sh -c` the given number of times."""
    text = "git push -f"
    for _ in range(levels):
        text = f"sh -c {shlex.quote(text)}"
    return text


def test_nesting_is_read_up_to_the_limit():
    assert INNER in commands(wrapped(shell_commands.MAX_NESTING))
    assert INNER not in commands(wrapped(shell_commands.MAX_NESTING + 1))


def test_open_quote_falls_back_to_whitespace():
    assert commands("git push -f 'x")[0][:3] == INNER


def test_assignments_are_returned():
    assignments, words = shell_commands.parse_prefixes(
        ["env", "GIT_DIR=/r/.git", "A=b=c", "git", "checkout", "x"]
    )
    assert assignments == {"GIT_DIR": "/r/.git", "A": "b=c"}
    assert words == ["git", "checkout", "x"]


@pytest.mark.parametrize(
    ("words", "expected"),
    [
        (["gh", "pr", "merge", "5"], ["pr", "merge", "5"]),
        (["gh", "-R", "o/r", "pr", "merge"], ["pr", "merge"]),
        (["gh", "--repo", "o/r", "pr", "merge"], ["pr", "merge"]),
        (["gh", "--repo=o/r", "pr", "merge"], ["pr", "merge"]),
        (["env", "gh.exe", "api", "x"], ["api", "x"]),
        (["git", "pr"], None),
        ([], None),
    ],
)
def test_gh_subcommand(words, expected):
    assert shell_commands.gh_subcommand(words) == expected
