"""Reads Dolev's last message in the session and the PR numbers it asks to merge.

Used by ask_before_merge.py (claude-config#301, spec S-3.11): a merge Dolev asked for in
his last message passes without a second approval window.

The transcript is the session's JSONL file (`transcript_path` in the hook input). His
last message is the newest of two kinds of rows:
1. A message he typed: `type: "user"`, `origin.kind: "human"`, text content, not
   `isMeta` (a skill or a reminder the harness injected).
2. An answer in the question window: a tool result whose `toolUseResult` holds
   `questions` and `answers` (AskUserQuestion).

Anything else is not his: a message from another session, a hook's text, another
tool's output. A missing or broken file reads as no request, so the window opens.
"""

import json
import re
from pathlib import Path

MERGE_WORD = re.compile(r"מזג|merge", re.IGNORECASE)
# "אל תמזג", "לא למזג", "don't merge": a request not to merge.
NEGATED = re.compile(
    r"(אל|לא|בלי)\s+(ל|ת)?מזג|(don'?t|do\s+not|not)\s+merge", re.IGNORECASE
)
NUMBER = re.compile(r"#(\d+)")


def typed_text(row: dict) -> str | None:
    """The text of a message Dolev typed, or None when the row is not one."""
    if row.get("type") != "user" or row.get("isMeta"):
        return None
    origin = row.get("origin")
    if not isinstance(origin, dict) or origin.get("kind") != "human":
        return None
    content = (row.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(parts) if parts else None
    return None


def window_text(row: dict) -> str | None:
    """The window's merge answers, each with its question; None when not a window.

    Only an answer that itself says to merge counts, so a number in another question
    of the same window is not a request. A window with no merge answer is still his
    last message: it returns "", which cancels an older request.
    """
    if row.get("type") != "user":
        return None
    result = row.get("toolUseResult")
    if not isinstance(result, dict):
        return None
    answers = result.get("answers")
    if not isinstance(answers, dict) or "questions" not in result:
        return None
    lines = [
        f"{question}\n{answer}"
        for question, answer in answers.items()
        if isinstance(answer, str) and MERGE_WORD.search(answer)
    ]
    return "\n\n".join(lines)


def last_message(transcript: Path) -> str | None:
    """Dolev's last message in the transcript: typed or chosen in the window."""
    last = None
    try:
        with transcript.open(encoding="utf-8") as lines:
            for line in lines:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                text = typed_text(row) or window_text(row)
                if text is not None:
                    last = text
    except OSError:
        return None
    return last


def requested_numbers(text: str | None) -> set[int]:
    """The numbers a message asks to merge: a merge word, no negation, and `#N`."""
    if not text or not MERGE_WORD.search(text) or NEGATED.search(text):
        return set()
    return {int(number) for number in NUMBER.findall(text)}


def requested_merges(transcript_path: object) -> set[int]:
    """The numbers Dolev's last message asks to merge; empty when there is none."""
    if not isinstance(transcript_path, str) or not transcript_path:
        return set()
    return requested_numbers(last_message(Path(transcript_path)))
