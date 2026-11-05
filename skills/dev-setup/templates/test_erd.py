"""The ERD page (docs/erd.html) shows exactly the tables, fields and links in code.

Template from ~/.claude/skills/dev-setup/templates/test_erd.py (~/.claude/rules/erd.md).
Fill in the values below: the imports that register every table, the page, its link.
Needs no database, so it runs locally even while CI is off.
"""

import json
import re
from pathlib import Path

import app.models  # noqa: F401  registers every table on Base.metadata
from app.db import Base

ERD_PAGE = Path(__file__).resolve().parents[2] / "docs" / "erd.html"
ARTIFACT_URL = "https://claude.ai/artifact/<id>"
# Every table has one; the page says so once instead of showing it in each box.
HIDDEN_FIELDS = {"created_at"}


def page_data() -> dict:
    """The JSON block the ERD page draws from."""
    html = ERD_PAGE.read_text(encoding="utf-8")
    block = re.search(
        r'<script type="application/json" id="erd-data">(.*?)</script>', html, re.S
    )
    assert block, f"{ERD_PAGE} has no erd-data block"
    return json.loads(block.group(1))


def model_fields() -> set[tuple[str, str, bool, bool]]:
    """(table, field, is_primary_key, is_required) for every column the page shows."""
    return {
        (table.name, column.name, column.primary_key, not column.nullable)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.name not in HIDDEN_FIELDS
    }


def page_fields(data: dict) -> set[tuple[str, str, bool, bool]]:
    """The same tuples as model_fields, read from the page. A key is always required."""
    return {
        (table, field, key == "PK", key == "PK" or bool(required))
        for table, spec in data["tables"].items()
        for field, _type, key, required in spec["rows"]
    }


def model_links() -> set[tuple[str, str, str]]:
    """(table, field, target table) for every foreign key."""
    return {
        (table.name, fk.parent.name, fk.column.table.name)
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
    }


def page_links(data: dict) -> set[tuple[str, str, str]]:
    """The same tuples as model_links, read from the page."""
    return {(table, field, target) for table, field, target, *_ in data["links"]}


def assert_same(name: str, on_page: set, in_models: set) -> None:
    """Fails with what to add to the page and what to remove from it."""
    missing, extra = sorted(in_models - on_page), sorted(on_page - in_models)
    assert not missing and not extra, (
        f"docs/erd.html is out of date ({name}).\n"
        f"  add or fix on the page: {missing}\n"
        f"  remove from the page:   {extra}\n"
        f"Update the erd-data block, then republish {ARTIFACT_URL} from the file."
    )


def test_erd_shows_every_table():
    data = page_data()
    assert_same("tables", set(data["tables"]), set(Base.metadata.tables))
    placed = {name for names in data["order"].values() for name in names}
    assert_same("tables placed in a column", placed, set(Base.metadata.tables))


def test_erd_shows_every_field():
    assert_same("fields", page_fields(page_data()), model_fields())


def test_erd_draws_every_foreign_key():
    assert_same("links", page_links(page_data()), model_links())
