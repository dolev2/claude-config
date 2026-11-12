"""pause_reason.py: whether an issue is paused, and the reason from its comments."""

import pause_reason
import pytest
from pause_reason import latest_reason, main, report

PAUSED = {"labels": [{"name": "status:explore"}, {"name": "paused"}]}
ACTIVE = {"labels": [{"name": "status:explore"}]}


def comment(body):
    return {"body": body}


def test_not_paused():
    assert report(ACTIVE, [comment("סיבת השהיה: לא משנה")]) == "not paused"


def test_paused_without_comments():
    assert report(PAUSED, []) == "paused"


def test_paused_with_one_reason():
    assert report(PAUSED, [comment("סיבת השהיה: מחכה לספק")]) == "paused\nמחכה לספק"


def test_the_newest_reason_wins():
    comments = [
        comment("סיבת השהיה: ישנה"),
        comment("סתם"),
        comment("סיבת השהיה: חדשה"),
    ]
    assert latest_reason(comments) == "חדשה"


def test_a_mention_in_the_middle_is_not_a_reason():
    assert latest_reason([comment("כתבתי סיבת השהיה: משהו")]) is None
    assert report(PAUSED, [comment("כתבתי סיבת השהיה: משהו")]) == "paused"


def test_leading_spaces_before_the_prefix():
    assert latest_reason([comment("  \nסיבת השהיה:  מחכה  ")]) == "מחכה"


def test_an_empty_reason_counts_as_none():
    assert report(PAUSED, [comment("סיבת השהיה:")]) == "paused"


@pytest.mark.parametrize("bad", ["abc", "0", "-3", ""])
def test_an_invalid_number_exits_non_zero(bad):
    with pytest.raises(SystemExit) as stop:
        main([bad, "--repo", "o/r"])
    assert stop.value.code != 0


def test_run_reads_the_issue_and_its_comments(monkeypatch, capsys):
    calls = []

    def fake_api(path):
        calls.append(path)
        return PAUSED

    def fake_api_list(path):
        calls.append(path)
        return [comment("סיבת השהיה: מחכה לדולב")]

    monkeypatch.setattr(pause_reason, "api", fake_api)
    monkeypatch.setattr(pause_reason, "api_list", fake_api_list)
    assert main(["#42", "--repo", "o/r"]) == 0
    assert capsys.readouterr().out == "paused\nמחכה לדולב\n"
    assert calls == ["repos/o/r/issues/42", "repos/o/r/issues/42/comments?per_page=100"]


def test_run_skips_comments_when_not_paused(monkeypatch, capsys):
    monkeypatch.setattr(pause_reason, "api", lambda path: ACTIVE)
    monkeypatch.setattr(pause_reason, "api_list", pytest.fail)
    assert main(["7", "--repo", "o/r"]) == 0
    assert capsys.readouterr().out == "not paused\n"
