import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generator"))

import retail  # noqa: E402


def test_same_seed_gives_identical_tables_and_another_seed_does_not(tmp_path: Path) -> None:
    first = retail.write(retail.generate(1), tmp_path / "a")
    second = retail.write(retail.generate(1), tmp_path / "b")
    other = retail.write(retail.generate(2), tmp_path / "c")
    assert first == second
    assert first != other


def test_tables_are_small_and_keys_line_up() -> None:
    rows = retail.generate(1)
    assert sum(len(table) for table in rows.values()) < 400_000
    customers = {row[0] for row in rows["customers"]}
    orders = {row[0] for row in rows["orders"]}
    products = {row[0] for row in rows["products"]}
    assert len(rows["customers"]) > len(customers)
    assert {row[1] for row in rows["orders"]} <= customers
    assert {row[1] for row in rows["order_items"]} == orders
    assert {row[2] for row in rows["order_items"]} <= products
    assert {row[1] for row in rows["payments"]} <= orders
