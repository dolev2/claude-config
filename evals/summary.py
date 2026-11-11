"""The lines run.py prints from a `claude plugin eval --json` result.

One line per skill ("dev-ship: 2 מתוך 2 עברו, עלות 1.20 דולר"), then each failed case
with the rule its failing grader stands for: the first line of the grader file's body.
"""

from __future__ import annotations

import json
from pathlib import Path


def skill_of(case: str, skills: tuple[str, ...]) -> str:
    """The skill a case belongs to: its name starts with the skill's name."""
    found = [s for s in skills if case == s or case.startswith(f"{s}-")]
    return max(found, key=len) if found else "other"


def rule_text(case_dir: Path, grader: str) -> str | None:
    """The rule a grader checks: the first non-empty body line of its file."""
    path = case_dir / "graders" / f"{grader}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    body = text.split("---", 2)[2] if text.startswith("---") else text
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return lines[0] if lines else None


def runs_of(case: dict) -> list[dict]:
    """The case's runs with the plugin loaded."""
    return case.get("arms", {}).get("with", []) or []


def case_cost(case: dict) -> float:
    return sum(
        (r.get("costUsd") or 0) + (r.get("judgeCostUsd") or 0) for r in runs_of(case)
    )


def failures(case: dict, plugin: Path) -> list[str]:
    """Why a case failed: each failing grader's rule, and each run error, once.

    The result's `dir` is relative to the plugin folder.
    """
    case_dir = plugin / case.get("dir", "")
    reasons: list[str] = []
    for run in runs_of(case):
        if run.get("error"):
            reasons.append(f"הריצה נגמרה בשגיאה: {run['error']}")
        for grader in run.get("graders", []):
            if grader.get("passed") or not grader.get("scored", True):
                continue
            rule = rule_text(case_dir, grader["name"])
            reasons.append(rule or f"{grader['name']}: {grader.get('explanation', '')}")
    return list(dict.fromkeys(reasons))


def model_of(case: dict) -> str | None:
    """The model that served the case's first run, read from its trace."""
    for run in runs_of(case):
        path = Path(run.get("tracePath") or "")
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            message = json.loads(line).get("message")
            if isinstance(message, dict) and message.get("model"):
                return message["model"]
    return None


def summarize(
    result: dict, skills: tuple[str, ...], plugin: Path = Path()
) -> tuple[list[str], bool]:
    """Printed lines, and whether any case that ran failed; plugin: the built plugin."""
    threshold = result.get("suite", {}).get("threshold", 1)
    by_skill: dict[str, list[dict]] = {}
    for case in result.get("cases", []):
        by_skill.setdefault(skill_of(case["name"], skills), []).append(case)
    lines, failed_lines = [], []
    for skill, cases in by_skill.items():
        ran = [c for c in cases if runs_of(c)]
        passed = [
            c for c in ran if c.get("aggregates", {}).get("score", 0) >= threshold
        ]
        cost = sum(case_cost(c) for c in cases)
        lines.append(
            f"{skill}: {len(passed)} מתוך {len(ran)} עברו, עלות {cost:.2f} דולר"
        )
        for case in ran:
            if case not in passed:
                failed_lines.append(f"נכשל: {case['name']}")
                failed_lines += [f"  {reason}" for reason in failures(case, plugin)]
    lines += failed_lines
    if result.get("partial"):
        reason = result.get("partialReason")
        unstarted = [c["name"] for c in result.get("cases", []) if not runs_of(c)]
        stop = "נעצר בתקרת העלות" if reason == "cost_ceiling" else f"נעצר: {reason}"
        lines.append(f"{stop}. לא הספיקו לרוץ: {', '.join(unstarted) or 'אין'}.")
    models = {m for c in result.get("cases", []) if (m := model_of(c))}
    total = result.get("costUsd") or 0
    lines.append(
        f"סך הכל: {total:.2f} דולר (שווי נומינלי), "
        f"{result.get('durationSeconds', 0):.0f} שניות, "
        f"מודל: {', '.join(sorted(models)) or 'לא ידוע'}"
    )
    return lines, bool(failed_lines)
