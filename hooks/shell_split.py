"""Splitting a shell line into the commands it runs, for the hooks.

A command often comes wrapped: `(git push -f)`, `if ...; then gh pr merge 5; fi`,
`env A=1 git ...`, `bash -c '...'`, `x=$(...)`. This module finds the command inside,
so each hook only matches plain words. It reads text and runs nothing.

Not read: PowerShell's own wrappers (`pwsh -Command`, `cmd /c`), a variable used as a
command (`$cmd`), and an `export` or alias set earlier in another tool call.
"""

import shlex
from pathlib import PurePath

from shell_strip import strip_text

# `(`, `)` and the backtick open or close a subshell; each one also ends a subcommand.
SEPARATOR_CHARS = ";&|\n()`"
# Words a shell reads before the command itself: `if git push -f; then ...`.
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}"}
# Run their argument as the command, after their own options. The value is the options
# that take the next word as their value; `timeout` also takes a duration after them.
WRAPPERS = {
    "builtin": set(),
    "command": set(),
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "exec": {"-a"},
    "nice": {"-n", "--adjustment"},
    "nohup": set(),
    "stdbuf": {"-i", "-o", "-e"},
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "-T"},
    "time": {"-f", "-o", "--format", "--output"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "xargs": {"-I", "-n", "-P", "-d", "-L", "-s", "-E", "-a", "--arg-file"},
}
# Shells whose `-c <text>` runs the text as a command; `eval` does the same.
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
SHELL_LONG_OPTIONS_WITH_VALUE = {"--rcfile", "--init-file"}
# How deep `bash -c "sh -c '...'"` is unwrapped; deeper text is not read.
MAX_NESTING = 3


def command_substitutions(command: str) -> list[str]:
    """The text inside each `$(...)` and backtick pair that is not in single quotes.

    Inside double quotes these still run, and shlex would keep them in one word.
    """
    found: list[str] = []
    quote = ""
    index = 0
    while index < len(command):
        char = command[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if quote == "'":
            quote = "" if char == "'" else quote
        elif char == "'" and not quote:
            quote = "'"
        elif char == '"':
            quote = "" if quote == '"' else '"'
        elif command.startswith("$(", index):
            end = closing_parenthesis(command, index + 2)
            found.append(command[index + 2 : end])
            index = end
        elif char == "`":
            end = command.find("`", index + 1)
            end = len(command) if end == -1 else end
            found.append(command[index + 1 : end])
            index = end
        index += 1
    return found


def closing_parenthesis(command: str, start: int) -> int:
    """The index of the `)` that closes the `(` just before start, or the text's end."""
    depth = 1
    for index in range(start, len(command)):
        if command[index] == "(":
            depth += 1
        elif command[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return len(command)


def split_words(command: str) -> list[list[str]]:
    """The words of each subcommand between `&&`, `;`, `|`, `(`, `)` or a newline."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=SEPARATOR_CHARS)
    lexer.whitespace = " \t\r"
    lexer.whitespace_split = True
    # shlex's comment reading would also swallow the newline that ends the subcommand.
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError:
        # Each line stays a subcommand of its own, so an open quote hides no later line.
        tokens = [
            word for line in command.split("\n") for word in [*line.split(), "\n"]
        ]
    subcommands: list[list[str]] = [[]]
    for token in tokens:
        if token and all(char in SEPARATOR_CHARS for char in token):
            subcommands.append([])
        else:
            subcommands[-1].append(token)
    return [words for words in subcommands if words]


def shell_text(words: list[str]) -> str | None:
    """The text a shell runs with `-c`: `bash -lc '<text>'`, `sh -o x -c '<text>'`."""
    has_c = False
    index = 1
    while index < len(words):
        word = words[index]
        if not word.startswith(("-", "+")):
            return word if has_c else None
        index += 1
        if word.startswith("--"):
            index += 1 if word in SHELL_LONG_OPTIONS_WITH_VALUE else 0
        elif word[-1] in "oO":
            index += 1
        has_c = has_c or (word.startswith("-") and "c" in word)
    return None


def split_string(words: list[str]) -> str | None:
    """The command `env -S '<text>'` or `env --split-string=<text>` runs, if any."""
    for index, word in enumerate(words):
        if PurePath(word).name.lower() != "env":
            continue
        for option_index, option in enumerate(words[index + 1 :], start=index + 1):
            if option in ("-S", "--split-string") and option_index + 1 < len(words):
                return words[option_index + 1]
            if option.startswith("--split-string="):
                return option.split("=", 1)[1]
            if not option.startswith("-") and not is_assignment(option):
                break
    return None


def nested_command(words: list[str]) -> str | None:
    """The text that `sh -c`, `eval` or `env -S` runs; None for anything else."""
    text = split_string(words)
    if text is not None:
        return text
    words = strip_prefixes(words)
    if not words:
        return None
    name = PurePath(words[0]).name.lower()
    if name == "eval":
        return " ".join(words[1:])
    return shell_text(words) if name in SHELLS else None


def split_subcommands(command: str, depth: int = 0) -> list[list[str]]:
    """The command's words, one list per subcommand it runs.

    Subcommands are split at `&&`, `;`, `|`, `(`, `)` and newlines; the text of
    `$(...)`, backticks, `sh -c`, `eval` and `env -S` is split again as commands of its
    own. Quotes are respected, so `git commit -m "a; git push -f"` stays one subcommand,
    and heredoc bodies and `#` comments are skipped. Text shlex cannot parse (an open
    quote) falls back to splitting each line on whitespace.
    """
    command = strip_text(command)
    subcommands = split_words(command)
    if depth >= MAX_NESTING:
        return subcommands
    inner = command_substitutions(command)
    inner += [text for words in subcommands if (text := nested_command(words))]
    for text in inner:
        subcommands += split_subcommands(text, depth + 1)
    return subcommands


def is_assignment(word: str) -> bool:
    """True for a `NAME=value` word."""
    return "=" in word and word.split("=")[0].isidentifier()


def skip_options(words: list[str], index: int, with_value: set[str]) -> int:
    """The index of the first word after a wrapper's options, from index on."""
    while index < len(words) and words[index].startswith("-"):
        word = words[index]
        index += 1
        if word == "--":
            break
        if word in with_value:
            index += 1
    return index


def parse_prefixes(words: list[str]) -> tuple[dict[str, str], list[str]]:
    """The `VAR=value` assignments before the command, and the command's own words.

    Shell keywords (`if`, `then`, `{`) and wrappers with their options (`env -i`,
    `timeout -s KILL 30`, `sudo -u root`) are dropped on the way.
    """
    assignments: dict[str, str] = {}
    index = 0
    while index < len(words):
        word = words[index]
        name = PurePath(word).name.lower()
        if word in KEYWORDS:
            index += 1
        elif is_assignment(word):
            key, value = word.split("=", 1)
            assignments[key] = value
            index += 1
        elif name in WRAPPERS:
            index = skip_options(words, index + 1, WRAPPERS[name])
            index += 1 if name == "timeout" else 0
        else:
            break
    return assignments, words[index:]


def strip_prefixes(words: list[str]) -> list[str]:
    """The words without leading keywords, `VAR=value` assignments and wrappers."""
    return parse_prefixes(words)[1]
