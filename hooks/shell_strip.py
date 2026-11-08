"""Removing the text of a shell line that runs nothing: heredoc bodies and `#` comments.

One pass reads quotes, `$(...)`, arithmetic and `${...}` the way bash does, so a `<<`
or a `#` counts only where bash reads code. It reads text and runs nothing.
"""

import re

# What may stand right before a `#` that starts a comment.
WORD_BREAKS = " \t\n;&|()"
# `<<EOF`, `<<-'EOF'`, `<< "EOF"`; not the `<<<` here-string, which has no body.
# The delimiter is the whole word: after `<<EOF.x`, bash waits for `EOF.x`, not `EOF`.
HEREDOC_START = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)(\w+)\2(?=[\s;&|()<>]|$)")
# The contexts a line can be in, innermost last on a stack:
# - "'", '"' and "$'": quotes, in which `<<` and `#` are text;
# - "(": code, in a subshell or `$(...)`; the line itself is code too;
# - "((": arithmetic, `$((...))` or `((...))`, where `<<` is a shift; "a(" is a
#   parenthesis inside it;
# - "${": a parameter expansion inside double quotes, where bash pairs `'` and `"`.
CODE = ("", "(")
CLOSERS = {'"': '"', "(": ")", "((": "))", "a(": ")", "${": "}"}


def strip_text(command: str) -> str:
    """The command without heredoc bodies and `# ...` comments, keeping the newlines.

    A `<<` opens a heredoc and a `#` at the start of a word starts a comment only where
    the innermost context is code: not inside quotes or arithmetic, but yes inside
    `"$(...)"`. A `"` inside a `"${...}"` comes back as `\\"`, so shlex reads it as
    text and keeps the outer quotes open, as bash does.
    """
    kept: list[str] = []
    pending: list[tuple[bool, str]] = []
    contexts: list[str] = []
    index = 0
    while index < len(command):
        is_code = (contexts[-1] if contexts else "") in CODE
        if command[index] == "\n" and pending and is_code:
            kept.append("\n")
            index = skip_heredoc_bodies(command, index + 1, pending)
            pending = []
            continue
        if is_code and starts_comment(command, index):
            end = command.find("\n", index)
            index = len(command) if end == -1 else end
            continue
        in_expansion = "${" in contexts
        step = heredoc_start(command, index, pending) if is_code else 0
        step = step or context_step(command, index, contexts)
        piece = command[index : index + step]
        kept.append('\\"' if in_expansion and piece == '"' else piece)
        index += step
    return "".join(kept)


def starts_comment(command: str, index: int) -> bool:
    """True for a `#` at the start of a word, so `$#`, `${#x}` and `a#b` stay."""
    return command[index] == "#" and (index == 0 or command[index - 1] in WORD_BREAKS)


def heredoc_start(command: str, index: int, pending: list[tuple[bool, str]]) -> int:
    """The length of a heredoc start at index, or 0; adds its delimiter to pending."""
    match = HEREDOC_START.match(command, index)
    if not match:
        return 0
    pending.append((bool(match[1]), match[3]))
    return len(match[0])


def context_step(command: str, index: int, contexts: list[str]) -> int:
    """How far to move past index; opens or closes a context on the way."""
    context = contexts[-1] if contexts else ""
    if command[index] == "\\" and context != "'":
        return 2
    if context in ("'", "$'"):
        if command[index] == "'":
            contexts.pop()
        return 1
    closer = CLOSERS.get(context, "")
    if closer and command.startswith(closer, index):
        contexts.pop()
        return len(closer)
    if context == "((" and command[index] == ")":
        # `$((1)+(2))`: one of the two opening parentheses is still open.
        contexts[-1] = "a("
        return 1
    opened = opening(command, index, context)
    if not opened:
        return 1
    contexts.append(opened[0])
    return opened[1]


def opening(command: str, index: int, context: str) -> tuple[str, int] | None:
    """The context that opens at index, with the length of its opener, or None."""
    if command.startswith("$((", index):
        return "((", 3
    if command.startswith("$(", index):
        return "(", 2
    char = command[index]
    if context in ("((", "a("):
        return ("a(", 1) if char == "(" else None
    if context in ('"', "${") and command.startswith("${", index):
        return "${", 2
    if context == '"':
        return None
    if command.startswith("$'", index):
        return "$'", 2
    if context in CODE and command.startswith("((", index):
        return "((", 2
    if char in "'\"" or (char == "(" and context in CODE):
        return char, 1
    return None


def skip_heredoc_bodies(
    command: str, start: int, delimiters: list[tuple[bool, str]]
) -> int:
    """The index after the bodies that start at start, one per delimiter, in order."""
    index = start
    for strip_tabs, delimiter in delimiters:
        while index < len(command):
            end = command.find("\n", index)
            end = len(command) if end == -1 else end
            line = command[index:end]
            index = end + 1
            line = line.lstrip("\t") if strip_tabs else line
            if line.rstrip("\r") == delimiter:
                break
    return min(index, len(command))
