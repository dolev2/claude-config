"""The Modern Web Guidance version is pinned once, in two places that agree (#456).

reference/web-guidance.md writes the commands with the version, and settings.json allows
exactly that command without a prompt. A version bump changes both in one PR; this
test fails when only one moved, when either says @latest, or when the permission rule
is gone.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOC = ROOT / "skills" / "dev-setup" / "reference" / "web-guidance.md"
SETTINGS = ROOT / "settings.json"

PACKAGE = "modern-web-guidance"
VERSION = re.compile(rf"{PACKAGE}@([\w.\-]+)")
EXACT = re.compile(r"\d+\.\d+\.\d+")


def pin_problems(doc_text: str, settings: dict) -> list[str]:
    """What is wrong with the pin across the doc and settings; empty when it holds."""
    doc_versions = set(VERSION.findall(doc_text))
    rules = [
        rule
        for rule in settings.get("permissions", {}).get("allow", [])
        if PACKAGE in rule
    ]
    rule_versions = {v for rule in rules for v in VERSION.findall(rule)}
    problems = []
    if not doc_versions:
        problems.append(f"web-guidance.md has no {PACKAGE}@<version> command")
    if not rules:
        problems.append(f"settings.json has no permission rule for {PACKAGE}")
    for where, versions in (
        ("web-guidance.md", doc_versions),
        ("settings.json", rule_versions),
    ):
        loose = sorted(v for v in versions if not EXACT.fullmatch(v))
        if loose:
            problems.append(f"{where} uses an unpinned version: {', '.join(loose)}")
        if len(versions) > 1:
            problems.append(
                f"{where} has more than one version: {', '.join(sorted(versions))}"
            )
    if doc_versions and rule_versions and doc_versions != rule_versions:
        problems.append(
            f"versions differ: web-guidance.md {sorted(doc_versions)}, "
            f"settings.json {sorted(rule_versions)}"
        )
    return problems


def settings_with(*rules: str) -> dict:
    """A settings dict whose allow list holds these rules."""
    return {"permissions": {"allow": ["mcp__github__get_me", *rules]}}


DOC_101 = f'npx -y {PACKAGE}@1.0.1 search "x"\nnpx -y {PACKAGE}@1.0.1 retrieve "y"\n'
RULE_101 = f"Bash(npx -y {PACKAGE}@1.0.1 *)"


def test_same_version_passes():
    assert pin_problems(DOC_101, settings_with(RULE_101)) == []


def test_different_version_fails():
    problems = pin_problems(DOC_101, settings_with(f"Bash(npx -y {PACKAGE}@1.0.0 *)"))
    assert any("versions differ" in p for p in problems)


def test_latest_in_doc_fails():
    doc = DOC_101 + f"npx -y {PACKAGE}@latest legacy-scan a.html --json\n"
    problems = pin_problems(doc, settings_with(RULE_101))
    assert any("unpinned" in p and "latest" in p for p in problems)


def test_latest_in_rule_fails():
    problems = pin_problems(DOC_101, settings_with(f"Bash(npx -y {PACKAGE}@latest *)"))
    assert any("settings.json uses an unpinned" in p for p in problems)


def test_missing_rule_fails():
    problems = pin_problems(DOC_101, settings_with())
    assert any("no permission rule" in p for p in problems)


def test_doc_without_version_fails():
    problems = pin_problems("no commands here\n", settings_with(RULE_101))
    assert any("no modern-web-guidance@" in p for p in problems)


def test_repo_pin_holds():
    """The real doc and settings.json agree on one exact version."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert pin_problems(DOC.read_text(encoding="utf-8"), settings) == []
