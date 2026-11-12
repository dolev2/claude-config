"""shell_commands.py: the commands a shell line runs, through wrappers and subshells."""

import shlex

import pytest
import shell_commands
import shell_split

INNER = ["git", "push", "-f"]


def commands(text: str) -> list[list[str]]:
    """Each subcommand of text, without its keywords, assignments and wrappers."""
    return [
        shell_split.strip_prefixes(words)
        for words in shell_split.split_subcommands(text)
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
        "bash --login -c 'git push -f'",
        "bash -o pipefail -c 'git push -f'",
        "env -S 'git push -f'",
        "env --split-string='git push -f'",
        "git fetch # update first\ngit push -f",
        "echo $# x; git push -f",
        'git commit -m "a # b"; git push -f',
        "x # don't\ngit push -f",
        'echo "see cat <<EOF in docs"\ngit push -f',
        "echo 'see cat <<EOF in docs'\ngit push -f",
        'echo "a\n<<EOF b"\ngit push -f',
        "# see cat <<EOF\ngit push -f",
        "cat <<EOF\nbody\nEOF\ngit push -f",
        "cat <<-EOF\n\tbody\n\tEOF\ngit push -f",
        "git commit -m \"$(cat <<'EOF'\ndon't\nEOF\n)\"\ngit push -f",
        "echo $'it\\'s <<EOF'\ngit push -f",
        "cat <<EOF.x\nhi\nEOF.x\ngit push -f",
        "cat <<'EOF'x\nhi\nEOFx\ngit push -f\nEOF",
        'cat <<EOF "x\ny"\nbody\nEOF\necho "<<EOF"\ngit push -f',
        "cat <<A <<B\na\nA\nb\nB\ngit push -f",
        "echo $((1<<EOF))\ngit push -f\nEOF",
        'echo "$(( (1+2) <<EOF ))"\ngit push -f\nEOF',
        "((x = 1<<EOF))\ngit push -f\nEOF",
        "echo $((1)+(2)) '$( #' ; git push -f",
        "echo $((1)+(2)) \"${x:-'\"'}\"\ngit push -f\necho it\\'s",
        "echo $((1)+(2)) <<EOF\nbody\nEOF\ngit push -f",
        "echo \"${x#'\"'}\"\ngit push -f\necho it\\'s",
        "echo \"${x:-'\"'}\"\ngit push -f\necho it\\'s",
        "echo \"${x/'\"'/q}\"\ngit push -f\necho it\\'s",
        'echo "${x:-"a b"}"\ngit push -f\necho it\\\'s',
        'echo "${x#\'"\'}" <<EOF\nbody\nEOF\ngit push -f',
        'echo "${x:-$(git push -f)}"',
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
        "# a note; git push -f",
        "echo done # then git push -f",
        "echo \"${x:-'; git push -f'}\"",
        'echo "${x#\'"\'}" <<EOF\ngit push -f\nEOF',
        "echo \"$(cat <<'EOF'\n(git push -f)\nEOF\n)\"",
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
    assert INNER in commands(wrapped(shell_split.MAX_NESTING))
    assert INNER not in commands(wrapped(shell_split.MAX_NESTING + 1))


def test_open_quote_falls_back_to_whitespace():
    assert commands("git push -f 'x")[0][:3] == INNER


def test_assignments_are_returned():
    assignments, words = shell_split.parse_prefixes(
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
        (["gh", "pr", "-R", "o/r", "merge", "5"], ["pr", "merge", "5"]),
        (["env", "gh.exe", "api", "x"], ["api", "x"]),
        (
            ["gh", "pr", "merge", "5", "--body", "-R", "--subject", "x"],
            ["pr", "merge", "5", "--body", "-R", "--subject", "x"],
        ),
        (
            ["gh", "pr", "merge", "5", "-b", "-R", "-t", "x"],
            ["pr", "merge", "5", "-b", "-R", "-t", "x"],
        ),
        (
            ["gh", "pr", "merge", "5", "-sb", "-R", "-t", "x"],
            ["pr", "merge", "5", "-sb", "-R", "-t", "x"],
        ),
        (
            ["gh", "pr", "merge", "5", "--body=-R", "x"],
            ["pr", "merge", "5", "--body=-R", "x"],
        ),
        (["gh", "pr", "merge", "5", "-bx", "-R", "o/r"], ["pr", "merge", "5", "-bx"]),
        (
            ["gh", "pr", "merge", "5", "--squash", "-R", "o/r"],
            ["pr", "merge", "5", "--squash"],
        ),
        (["gh", "api", "-X", "PUT", "-R", "o/r", "x"], ["api", "-X", "PUT", "x"]),
        (["git", "pr"], None),
        ([], None),
    ],
)
def test_gh_subcommand(words, expected):
    assert shell_commands.gh_subcommand(words) == expected


@pytest.mark.parametrize(
    ("command", "include_auto", "expected"),
    [
        ("gh pr merge 5 --auto", True, True),
        ("gh pr merge 5 --auto", False, False),
        ("gh -R a/b pr merge 5", False, True),
        ("gh pr view 5", True, False),
    ],
)
def test_is_gh_pr_merge(command, include_auto, expected):
    words = shlex.split(command)
    assert shell_commands.is_gh_pr_merge(words, include_auto) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("gh pr merge 5 --squash", True),
        ("gh pr merge 5 --auto --squash", False),
        ("gh api -X PUT repos/a/b/pulls/5/merge", True),
        ("gh api repos/a/b/pulls/5/merge", False),
        ("gh alias set m 'pr merge'", False),
        ("echo hi && gh pr merge 5", True),
    ],
)
def test_is_shell_pr_merge(command, expected):
    assert shell_commands.is_shell_pr_merge(command) is expected
