import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import follow_ups  # noqa: E402

REPO = "https://api.github.com/repos/acme/widgets/issues"
PRODUCT = "**מוצר:** המסך של הלקוחות בלי עיצוב.\\\n   למה לא בתוכנית: רק עסקאות."
PROCESS = "**תהליך:** מה קרה: ... הכלל המוצע: ... הריפו: dolev2/claude-config."


def issue(number, state="open", labels=(), created="2026-11-02T00:00:00Z"):
    return {
        "number": number,
        "state": state,
        "created_at": created,
        "labels": [{"name": name} for name in labels],
    }


def comment(number, body, cid=1):
    return {
        "issue_url": f"{REPO}/{number}",
        "html_url": f"https://github.com/acme/widgets/issues/{number}#issuecomment-{cid}",
        "body": body,
    }


def hand_off(*tasks):
    listed = "\n".join(f"{i}. {task}" for i, task in enumerate(tasks, 1))
    return f"סקירת קוד: 2 ממצאים.\n\n#### משימות המשך\n{listed}\n\nהשלב הבא: מיזוג."


def run(issues, comments, pulls=()):
    return follow_ups.collect(issues, comments, list(pulls))


def test_a_product_and_a_process_task_both_come_out_with_kind_and_key():
    pulls = [{"number": 9, "head": {"sha": "abc"}, "body": "Closes #1"}]
    result = run([issue(1)], [comment(1, hand_off(PRODUCT, PROCESS))], pulls)
    tasks = result["follow_ups"]
    assert [t["kind"] for t in tasks] == ["מוצר", "תהליך"]
    assert all(len(t["key"]) == 10 and t["pr"] == 9 for t in tasks)
    assert tasks[0]["text"].startswith("**מוצר:**") and "רק עסקאות" in tasks[0]["text"]
    assert "השלב הבא" not in tasks[1]["text"]
    assert result["follow_up_gaps"] == []


def test_no_follow_ups_is_no_task_and_no_gap():
    body = "#### משימות המשך\nאין משימות המשך\n"
    result = run([issue(1, labels=["status:in-review"])], [comment(1, body)])
    assert result == {"follow_ups": [], "follow_up_gaps": []}


def test_a_task_already_asked_on_its_issue_is_left_out_but_not_on_another():
    key = follow_ups.task_key(PRODUCT)
    asked = f"{follow_ups.MARKER}\n<!-- follow-up: {key} -->\nמוצר: לבקלוג."
    comments = [
        comment(1, hand_off(PRODUCT)),
        comment(2, hand_off(PRODUCT), cid=2),
        comment(1, asked, cid=3),
    ]
    result = run([issue(1), issue(2)], comments)
    assert [t["issue"] for t in result["follow_ups"]] == [2]


def test_a_task_repeated_by_a_repair_round_comes_out_once():
    comments = [comment(1, hand_off(PRODUCT)), comment(1, hand_off(PRODUCT), cid=2)]
    result = run([issue(1)], comments)
    assert len(result["follow_ups"]) == 1
    assert result["follow_ups"][0]["comment_url"].endswith("issuecomment-1")


def test_a_closed_issue_keeps_a_task_not_yet_asked():
    result = run([issue(1, state="closed")], [comment(1, hand_off(PROCESS))])
    assert [t["kind"] for t in result["follow_ups"]] == ["תהליך"]


def test_in_review_without_the_heading_and_a_task_without_a_kind_are_gaps():
    issues = [issue(1, labels=["status:in-review"]), issue(2)]
    comments = [
        comment(1, "סקירת קוד: אין ממצאים."),
        comment(2, hand_off("סתם משימה בלי סוג", PRODUCT), cid=2),
    ]
    result = run(issues, comments)
    assert [t["issue"] for t in result["follow_ups"]] == [2]
    gaps = {(g["issue"], g["message"].split(":")[0]) for g in result["follow_up_gaps"]}
    assert gaps == {
        (1, "בהערת המסירה אין את הכותרת #### משימות המשך"),
        (2, "משימת המשך בלי סוג"),
    }


def test_an_orchestrator_comment_quoting_the_heading_is_not_a_hand_off():
    quoted = f"{follow_ups.MARKER}\n{hand_off(PRODUCT)}"
    result = run([issue(1, labels=["status:in-review"])], [comment(1, quoted)])
    assert result["follow_ups"] == []
    assert [g["issue"] for g in result["follow_up_gaps"]] == [1]


def test_comments_of_issues_outside_the_milestone_are_ignored():
    result = run([issue(1)], [comment(5, hand_off(PRODUCT))])
    assert result == {"follow_ups": [], "follow_up_gaps": []}


def test_the_section_ends_at_the_next_heading():
    body = hand_off(PRODUCT) + "\n### עוד\n1. **מוצר:** לא שייך."
    result = run([issue(1)], [comment(1, body)])
    assert len(result["follow_ups"]) == 1


def test_main_with_a_milestone_that_does_not_exist_exits(monkeypatch):
    monkeypatch.setattr(follow_ups, "api_list", lambda path: [{"title": "Sprint 1"}])
    with pytest.raises(SystemExit, match="No milestone named"):
        follow_ups.main(["--repo", "acme/widgets", "--milestone", "Sprint 9"])


def test_main_prints_both_keys(monkeypatch, capsys):
    sent = []
    milestone = {"title": "Sprint 1", "number": 3, "created_at": "2026-11-01T00:00:00Z"}
    lists = {
        "milestones": [milestone],
        "issues?milestone=3": [issue(1, created="2026-10-20T00:00:00Z")],
        "comments": [comment(1, hand_off(PRODUCT))],
    }

    def fake_list(path):
        sent.append(path)
        return next(rows for part, rows in lists.items() if part in path)

    monkeypatch.setattr(follow_ups, "api_list", fake_list)
    monkeypatch.setattr(follow_ups, "api", lambda path: [])
    follow_ups.main(["--repo", "acme/widgets", "--milestone", "Sprint 1"])
    result = json.loads(capsys.readouterr().out)
    assert [t["issue"] for t in result["follow_ups"]] == [1]
    assert result["follow_up_gaps"] == []
    assert "since=2026-10-20T00:00:00Z" in sent[-1]


def test_a_hash_inside_a_task_does_not_end_the_section():
    body = hand_off(PRODUCT + "\n   #338 משכתב את process-tasks.md", PROCESS)
    result = run([issue(1)], [comment(1, body)])
    assert [t["kind"] for t in result["follow_ups"]] == ["מוצר", "תהליך"]


def test_a_list_after_the_tasks_is_not_more_tasks():
    body = hand_off(PRODUCT) + "\n**הצעד הבא:**\n1. לסקור.\n2. למזג."
    result = run([issue(1)], [comment(1, body)])
    assert len(result["follow_ups"]) == 1
    assert result["follow_up_gaps"] == []


def test_a_line_after_a_backslash_belongs_to_the_task():
    body = hand_off("**מוצר:** א.\\\nלמה לא בתוכנית: ב.")
    result = run([issue(1)], [comment(1, body)])
    assert "למה לא בתוכנית" in result["follow_ups"][0]["text"]


def test_no_follow_ups_as_a_list_item_is_no_gap():
    result = run([issue(1)], [comment(1, hand_off("אין משימות המשך."))])
    assert result == {"follow_ups": [], "follow_up_gaps": []}


def test_a_closed_issue_and_a_repeated_task_give_no_gap_again():
    kindless = hand_off("סתם משימה")
    comments = [comment(1, kindless), comment(1, kindless, cid=2), comment(2, kindless)]
    result = run([issue(1), issue(2, state="closed")], comments)
    assert [g["issue"] for g in result["follow_up_gaps"]] == [1]
