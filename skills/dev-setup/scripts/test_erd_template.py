"""templates/erd.html: the example erd-data block is one the drawing code can draw.

The comparison with the models lives in templates/test_erd.py and runs in each repo,
where SQLAlchemy is installed. Here only the block's own consistency is checked.
"""

import copy
import json
import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "erd.html"
COLORS = {f"c{n}" for n in range(1, 7)}


def template_data() -> dict:
    """The JSON block of the template page."""
    html = TEMPLATE.read_text(encoding="utf-8")
    block = re.search(
        r'<script type="application/json" id="erd-data">(.*?)</script>', html, re.S
    )
    assert block, f"{TEMPLATE} has no erd-data block"
    return json.loads(block.group(1))


def problems(data: dict) -> list[str]:
    """Everything in the block that would break the drawing, one line each."""
    tables = data["tables"]
    found = []
    placed = [name for names in data["order"].values() for name in names]
    for name in sorted(set(tables) | set(placed)):
        if placed.count(name) != 1:
            found.append(f"{name} is placed {placed.count(name)} times in order")
    targets = {target for _table, _field, target, *_ in data["links"]}
    colors = [spec["color"] for spec in tables.values() if "color" in spec]
    for name, spec in tables.items():
        if spec.get("color", "c1") not in COLORS:
            found.append(f"{name} has color {spec['color']}, not one of c1..c6")
        if "color" in spec and name not in targets:
            found.append(f"{name} has a color but no link points to it")
    for color in sorted({c for c in colors if colors.count(c) > 1}):
        found.append(f"{color} is used by more than one table")
    columns = len(data["order"])
    for table, field, target, gutter, _meaning in data["links"]:
        fields = {row[0] for row in tables.get(table, {}).get("rows", [])}
        if field not in fields:
            found.append(f"link from {table}.{field}, which is not on the page")
        if "id" not in {row[0] for row in tables.get(target, {}).get("rows", [])}:
            found.append(f"link to {target}.id, which is not on the page")
        elif "color" not in tables[target]:
            found.append(f"{target} is a link target without a color")
        if not 0 <= gutter < columns:
            found.append(f"{table}.{field} uses gutter {gutter}, beyond the columns")
    return found


def test_template_block_is_consistent():
    assert problems(template_data()) == []


def test_template_shows_a_link_and_a_legend_color():
    data = template_data()
    assert data["links"]
    assert any("color" in spec for spec in data["tables"].values())


def test_broken_block_names_each_problem():
    data = copy.deepcopy(template_data())
    data["links"].append(["orders", "missing", "customers", 9, ""])
    data["tables"]["orders"]["color"] = "red"
    data["order"]["1"].append("orders")
    assert problems(data) == [
        "orders is placed 2 times in order",
        "orders has color red, not one of c1..c6",
        "orders has a color but no link points to it",
        "link from orders.missing, which is not on the page",
        "orders.missing uses gutter 9, beyond the columns",
    ]


def test_link_to_a_missing_table_is_named():
    data = copy.deepcopy(template_data())
    data["links"].append(["orders", "customer_id", "missing", 1, ""])
    assert problems(data) == ["link to missing.id, which is not on the page"]


def test_color_off_target_and_shared_color_are_named():
    data = copy.deepcopy(template_data())
    data["tables"]["orders"]["color"] = "c1"
    assert problems(data) == [
        "orders has a color but no link points to it",
        "c1 is used by more than one table",
    ]


def test_target_without_color_is_named():
    data = copy.deepcopy(template_data())
    del data["tables"]["customers"]["color"]
    assert problems(data) == ["customers is a link target without a color"]
