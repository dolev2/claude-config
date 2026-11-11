"""Reads Dolev's last message in the session and the PR numbers it asks to merge.

Used by ask_before_merge.py (claude-config#301, spec S-3.11): a merge Dolev asked for in
his last message passes without a second approval window.

The transcript is the session's JSONL file (`transcript_path` in the hook input). His
last message is the newest of three kinds of rows:
1. A message he typed: `type: "user"`, `origin.kind: "human"`, text content, not
   `isMeta` (a skill or a reminder the harness injected).
2. A message he typed while a turn was running: `type: "attachment"` with an
   `attachment` of type `queued_command`, the same `origin`, and the text in `prompt`.
3. An answer in the question window: a tool result of an `AskUserQuestion` call, whose
   `toolUseResult` holds `questions` and `answers`.

Anything else is not his: a message from another session, a hook's text, another
tool's output. A missing or broken file reads as no request, so the window opens.
"""

import json
import re
from pathlib import Path

# A request to merge, not a word that only holds "merge" ("merged", "emergency", "מזגת",
# "נמזג"): the Hebrew imperative or infinitive, or English "merge" right before "#N".
MERGE_WORD = re.compile(
    r"(?<![\u0590-\u05ff])(תמזג|למזג)(?![\u0590-\u05ff])|\bmerge\s+(the\s+pr\s+)?#\d",
    re.IGNORECASE,
)
# Any negation in the message makes it no request; the window then asks.
NEGATION = re.compile(
    r"(?<![\u0590-\u05ff])(ו?לא|אל|בלי)(?![\u0590-\u05ff])|\b(not|don'?t|no)\b",
    re.IGNORECASE,
)
NUMBER = re.compile(r"#(\d+)")
WINDOW_TOOL = "AskUserQuestion"


def is_human(row: dict) -> bool:
    """True when the row says a person wrote it: `origin.kind` is "human", not meta."""
    origin = row.get("origin")
    return (
        not row.get("isMeta")
        and isinstance(origin, dict)
        and origin.get("kind") == "human"
    )


def queued_text(row: dict) -> str | None:
    """The text Dolev typed while a turn ran (a queued command), or None."""
    attachment = row.get("attachment")
    if row.get("type") != "attachment" or not isinstance(attachment, dict):
        return None
    if attachment.get("type") != "queued_command" or not is_human(attachment):
        return None
    prompt = attachment.get("prompt")
    return prompt if isinstance(prompt, str) else ""


def typed_text(row: dict) -> str | None:
    """The text of a message Dolev typed, or None when the row is not one."""
    if row.get("type") != "user" or not is_human(row):
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


def window_tool_ids(row: dict) -> set[str]:
    """The ids of the `AskUserQuestion` calls in an assistant row."""
    if row.get("type") != "assistant":
        return set()
    content = (row.get("message") or {}).get("content")
    if not isinstance(content, list):
        return set()
    return {
        part.get("id")
        for part in content
        if isinstance(part, dict)
        and part.get("type") == "tool_use"
        and part.get("name") == WINDOW_TOOL
        and isinstance(part.get("id"), str)
    }


def answers_window(row: dict, window_ids: set[str]) -> bool:
    """True when the row's tool result answers one of the `AskUserQuestion` calls."""
    content = (row.get("message") or {}).get("content")
    if not isinstance(content, list):
        return False
    return any(
        isinstance(part, dict)
        and part.get("type") == "tool_result"
        and part.get("tool_use_id") in window_ids
        for part in content
    )


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


def message_text(row: dict, window_ids: set[str]) -> str | None:
    """The text of the row when it is a message from Dolev, else None."""
    text = typed_text(row)
    if text is None:
        text = queued_text(row)
    if text is None and answers_window(row, window_ids):
        text = window_text(row)
    return text


def last_message(transcript: Path) -> str | None:
    """Dolev's last message in the transcript: typed, queued or chosen in the window."""
    last = None
    window_ids: set[str] = set()
    try:
        with transcript.open(encoding="utf-8") as lines:
            for line in lines:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                window_ids |= window_tool_ids(row)
                text = message_text(row, window_ids)
                if text is not None:
                    last = text
    except OSError:
        return None
    return last


def requested_numbers(text: str | None) -> set[int]:
    """The numbers a message asks to merge: a merge word, no negation, and `#N`."""
    if not text or not MERGE_WORD.search(text) or NEGATION.search(text):
        return set()
    return {int(number) for number in NUMBER.findall(text)}


def requested_merges(transcript_path: object) -> set[int]:
    """The numbers Dolev's last message asks to merge; empty when there is none."""
    if not isinstance(transcript_path, str) or not transcript_path:
        return set()
    return requested_numbers(last_message(Path(transcript_path)))
