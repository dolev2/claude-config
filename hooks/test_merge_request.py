"""merge_request.py: the PR numbers Dolev's last message asks to merge (S-3.11)."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "merge_request.py"
spec = importlib.util.spec_from_file_location("merge_request", SCRIPT)
merge_request = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge_request)


def typed(text: str, kind: str = "human", meta: bool = False) -> dict:
    """A transcript row for a message typed in the chat."""
    row = {"type": "user", "origin": {"kind": kind}, "message": {"content": text}}
    if meta:
        row["isMeta"] = True
    return row


def window(question: str, answer: str) -> dict:
    """A transcript row for an answer chosen in the question window."""
    return {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": "answered"}]},
        "toolUseResult": {
            "questions": [{"question": question}],
            "answers": {question: answer},
        },
    }


def tool_output(text: str) -> dict:
    """A transcript row for another tool's output."""
    return {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": text}]},
        "toolUseResult": {"stdout": text},
    }


def write_transcript(tmp_path: Path, rows: list, broken: bool = False) -> str:
    path = tmp_path / "session.jsonl"
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    if broken:
        lines.insert(0, "{not json")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([typed("תמזג את #12")], {12}),
        ([typed("תמזג את #12 ו-#13")], {12, 13}),
        ([typed("please merge #7")], {7}),
        ([typed("dolev2/claude-config#40 תמזג")], {40}),
        ([window("למזג את #299?", "תמזג (מומלץ)")], {299}),
        ([window("מה הלאה?", "תמזג את #5")], {5}),
        # an older request, then another message: the request is gone
        ([typed("תמזג את #12"), typed("מצוין")], set()),
        ([typed("תמזג את #12"), window("לאשר את #20?", "מאשר")], set()),
        # a window answer that is not a merge leaves no number behind
        ([window("לאשר את #20?", "מאשר, תתחיל לקודד")], set()),
        # no merge word, or a negation
        ([typed("מה המצב של #12?")], set()),
        ([typed("אל תמזג את #12")], set()),
        ([typed("don't merge #12")], set()),
        # a merge without a number
        ([typed("תמזג")], set()),
        # not Dolev: another session, an injected skill, a tool's output
        ([typed("תמזג את #12", kind="peer")], set()),
        ([typed("תמזג את #12", meta=True)], set()),
        ([tool_output("תמזג את #12")], set()),
        # Dolev's request stays his last message when a tool runs after it
        ([typed("תמזג את #12"), tool_output("ok")], {12}),
    ],
)
def test_requested_merges(tmp_path, rows, expected):
    assert merge_request.requested_merges(write_transcript(tmp_path, rows)) == expected


def test_broken_line_is_skipped(tmp_path):
    path = write_transcript(tmp_path, [typed("תמזג את #3")], broken=True)
    assert merge_request.requested_merges(path) == {3}


def test_typed_text_parts(tmp_path):
    row = typed("")
    row["message"]["content"] = [{"type": "text", "text": "תמזג את #8"}]
    assert merge_request.requested_merges(write_transcript(tmp_path, [row])) == {8}


@pytest.mark.parametrize("path", [None, "", 5])
def test_no_transcript_path(path):
    assert merge_request.requested_merges(path) == set()


def test_missing_file(tmp_path):
    assert merge_request.requested_merges(str(tmp_path / "missing.jsonl")) == set()
