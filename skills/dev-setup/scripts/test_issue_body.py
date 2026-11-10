"""issue_body.py: the "אפיון:" line (claude-config #226)."""

import pytest
from issue_body import dependency_line, spec_line


@pytest.mark.parametrize(
    "context, expected",
    [
        ("אפיון: docs/specs/pipeline.md S-3.2", ("docs/specs/pipeline.md", ["S-3.2"])),
        (
            "תלוי ב: #4\nאפיון: `docs/specs/a.md` S-1.1, S-1.2, S-1.1",
            ("docs/specs/a.md", ["S-1.1", "S-1.2"]),
        ),
        ("Spec: docs/specs/a.md S-2.1", ("docs/specs/a.md", ["S-2.1"])),
        ("- אפיון: docs/specs/a.md S-2.1", ("docs/specs/a.md", ["S-2.1"])),
        (
            "אפיון: [docs/specs/a.md](docs/specs/a.md) S-1.1",
            ("docs/specs/a.md", ["S-1.1"]),
        ),
        (
            "אפיון: https://github.com/o/r/blob/main/docs/specs/a.md S-1.1",
            ("docs/specs/a.md", ["S-1.1"]),
        ),
        ("אפיון: S-2.1", ("", ["S-2.1"])),
        ("אפיון: docs/specs/a.md", ("docs/specs/a.md", [])),
        ("תלוי ב: #4\nשום דבר על אפיון כאן", None),
        ("", None),
    ],
)
def test_spec_line(context, expected):
    assert spec_line(context) == expected


def test_spec_line_leaves_the_dependency_line_alone():
    context = "תלוי ב: #4, #7\nאפיון: docs/specs/a.md S-1.1"
    assert dependency_line(context) == [4, 7]
