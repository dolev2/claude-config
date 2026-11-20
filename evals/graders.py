"""Read the pattern of a regex grader, and find what the eval engine cannot read in it.

The engine that runs the cases matches a grader's pattern in JavaScript, not in Python.
Python's start and end of input anchors and inline flags are not JavaScript, so a grader
that uses them fails even when the skill was right (S-1.49, S-1.71).
"""

import re
from pathlib import Path

PATTERN_LINE = "pattern: '"

# An odd number of backslashes before the letter makes it an anchor; an even number
# escapes the backslashes themselves, and the letter is plain text.
ANCHOR = re.compile(r"(?<!\\)(?:\\\\)*\\([AZz])")
# "(?" then flag letters, then ")" or ":". Groups like "(?:", "(?=" and "(?<" have no
# flag letter right after "(?", and an escaped "\(" opens no group.
INLINE_FLAG = re.compile(r"(?<!\\)(?:\\\\)*\((\?[aiLmsux]*(?:-[aiLmsux]+)?[:)])")

ANCHOR_FIX = {
    "A": "^ (with no flag, the start of the input)",
    "Z": "$ (with no flag, the end of the input)",
    "z": "$ (with no flag, the end of the input)",
}
FLAG_FIX = {
    "m": r"a whole line as (?:^|\n)<the line>\n",
    "s": r"[\s\S] in place of .",
    "i": "both cases of each letter, or a character class",
}


def regex_pattern(grader: Path) -> str:
    """The pattern of a regex grader, from its single-quoted `pattern:` line."""
    for line in grader.read_text(encoding="utf-8").splitlines():
        if line.startswith(PATTERN_LINE) and line.endswith("'"):
            return line[len(PATTERN_LINE) : -1].replace("''", "'")
    raise AssertionError(
        f"{grader}: no single-quoted `pattern: '...'` line on one line"
    )


def is_regex_grader(grader: Path) -> bool:
    """Whether the grader's front matter says `type: regex`."""
    return "type: regex" in grader.read_text(encoding="utf-8").splitlines()


def unsupported(pattern: str) -> list[str]:
    """What the engine cannot read in the pattern: one line per find, with its fix."""
    finds = []
    for match in ANCHOR.finditer(pattern):
        letter = match.group(1)
        finds.append(f"anchor \\{letter}: write {ANCHOR_FIX[letter]}")
    for match in INLINE_FLAG.finditer(pattern):
        group = match.group(1)
        flags = group[1:-1].replace("-", "")
        if not flags:
            continue
        fixes = "; ".join(
            FLAG_FIX.get(flag, "no flag") for flag in dict.fromkeys(flags)
        )
        finds.append(f"inline flag ({group}: write {fixes}")
    return finds
