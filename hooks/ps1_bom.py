"""PostToolUse hook: adds a UTF-8 BOM to a .ps1 that Write or Edit left without one.

Wired in settings.json for the Write, Edit and MultiEdit tools (claude-config#63), run
by python3 or python, whichever exists, from $HOME/.claude/hooks/.

Windows PowerShell 5.1 reads a .ps1 without a BOM in the local code page, and Hebrew in
it turns to gibberish (rules/env-windows.md). The BOM does no harm to PowerShell 7.

The tool already wrote the file, so there is nothing to block: the hook always exits 0,
and on any error it leaves the file as it was.
"""

import sys
from pathlib import Path

from shell_commands import edit_target, read_event

UTF8_BOM = b"\xef\xbb\xbf"
# Already encoded with a BOM of their own; a UTF-8 BOM in front would break them.
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


def add_bom(path: Path) -> bool:
    """Prefix the .ps1 file at path with a UTF-8 BOM; True when the file changed."""
    if path.suffix.lower() != ".ps1" or not path.is_file():
        return False
    content = path.read_bytes()
    if content.startswith(UTF8_BOM) or content.startswith(UTF16_BOMS):
        return False
    path.write_bytes(UTF8_BOM + content)
    return True


def main() -> int:
    """Read the tool call from stdin and fix its file; always return 0."""
    event = read_event(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    if event is None:
        return 0
    try:
        path = edit_target(event)
        if path is not None:
            add_bom(path)
    except (OSError, ValueError):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
