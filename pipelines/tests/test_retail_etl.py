from datetime import datetime
from decimal import Decimal

import openpyxl
import psycopg
import pyarrow.parquet as pq
import pytest

from retail_etl import pipeline
from retail_etl.clean import clean
from retail_etl.config import SCHEMA, SHEETS, TABLE
from retail_etl.pipeline import StepError

UK = "United Kingdom"


def r(tag, invoice, code, description, quantity, when, price, customer, country=UK):
    return tag, (invoice, code, description, quantity, datetime.fromisoformat(f"2010-12-01 {when}"), price, customer, country)


FIRST = [
    r("sale", "536001", "85123A", " WHITE  HANGING  HEART ", 6, "08:00", 2.55, 17850),
    r("duplicate", "536001", "85123A", " WHITE  HANGING  HEART ", 6, "08:00", 2.55, 17850),
    r("sale", 536002, 22423.0, "  ", 2, "08:05", 5, None),
    r("sale", "536003", "71053", "METAL LANTERN", 3, "08:10", 3.39, 13047),
    r("duplicate", "536003", "71053", "METAL LANTERN", 3, "08:10", 3.39, 13047),
    r("sale", "536004", "84406B", "CREAM CUPID", 8, "08:15", 2.75, 13047),
    r("test", "536005", "TEST001", "test", 1, "08:20", 10, None),
    r("test", "536005", "test002 ", "test", 1, "08:20", 10, None),
    r("bad_debt", "A536006", "B", "Adjust bad debt", 1, "08:25", -11062.06, None),
    r("bad_debt", "536006", "b", "Bad debt", 1, "08:25", 5, None),
    r("stock_adjustment", "536007", "22139", "damaged", -5, "08:30", 0, None),
    r("free_item", "536008", "22140", "sample given", 1, "08:35", 0, 12647),
    r("non_merchandise", "536009", "POST", "POSTAGE", 1, "08:40", 18, 12583),
    r("non_merchandise", "536010", "gift_0001_20", "Dotcomgiftshop", 1, "08:45", 16.67, None),
    r("non_merchandise", "C536011", "AMAZONFEE", "AMAZON FEE", -1, "08:50", 50, None),
    r("non_merchandise", "536012", "m ", "Manual", 1, "08:55", 5, None),
    r("void", "540001", "21730", "GLASS STAR", 4, "09:00", 3.0, 14001),
    r("void", "C540002", "21730", "GLASS STAR", -4, "10:00", 3.0, 14001),
    r("sale", "540010", "22960", "JAM MAKING SET", 10, "09:00", 1.0, 14002),
    r("return", "C540011", "22960", "JAM MAKING SET", -3, "10:00", 1.0, 14002),
    r("return", "C540012", "22960", "JAM MAKING SET", -10, "11:00", 1.0, 14002),
    r("void", "540020", "22961", "JAM JAR", 5, "09:00", 2.0, 14003),
    r("sale", "540021", "22961", "JAM JAR", 5, "09:10", 2.0, 14003),
    r("return", "C540022", "22961", "JAM JAR", -2, "09:30", 2.0, 14003),
    r("void", "C540023", "22961", "JAM JAR", -5, "10:00", 2.0, 14003),
    r("sale", "540030", "22962", "BOWL", 5, "08:00", 1.5, 14004),
    r("return", "C540031", "22962", "BOWL", -5, "12:01", 1.5, 14004),
    r("void", "540040", "22963", "PLATE", 5, "08:00", 2.0, 14005),
    r("void", "C540041", "22963", "PLATE", -5, "12:00", 2.0, 14005),
    r("sale", "540050", "22964", "CUP", 5, "08:00", 2.0, 14006),
    r("return", "C540051", "22964", "CUP", -5, "08:30", 2.5, 14006),
    r("void", "C540060", "22965", "SPOON", -2, "09:00", 4.0, 14007),
    r("void", "540061", "22965", "SPOON", 2, "09:00", 4.0, 14007),
    r("return", "C540070", "22966", "FORK", -1, "08:00", 6.0, 14008),
    r("sale", "540071", "22966", "FORK", 1, "09:00", 6.0, 14008),
    r("sale", "540080", "22967", "KNIFE", 3, "08:00", 1.25, None),
    r("return", "C540081", "22967", "KNIFE", -3, "08:30", 1.25, None),
]
SECOND = [
    r("overlap", "536003", "71053", "METAL LANTERN", 3, "08:10", 3.39, 13047),
    r("overlap", "536003", "71053", "METAL LANTERN", 3, "08:10", 3.39, 13047),
    r("duplicate", "536003", "71053", "METAL LANTERN", 3, "08:10", 3.39, 13047),
    r("overlap", "536001", "85123A", " WHITE  HANGING  HEART ", 6, "08:00", 2.55, 17850),
    r("sale", "541001", "22968", "MUG", 1, "08:00", 1.0, 15000),
    r("duplicate", "541001", "22968", "MUG", 1, "08:00", 1.0, 15000),
]


def at(when):
    return datetime.fromisoformat(f"2010-12-01 {when}")


EXPECTED = [
    ("536001", "85123A", "WHITE HANGING HEART", 6, at("08:00"), Decimal("2.5500"), 17850, UK, False),
    ("536002", "22423", None, 2, at("08:05"), Decimal("5.0000"), None, UK, False),
    ("536003", "71053", "METAL LANTERN", 3, at("08:10"), Decimal("3.3900"), 13047, UK, False),
    ("536004", "84406B", "CREAM CUPID", 8, at("08:15"), Decimal("2.7500"), 13047, UK, False),
    ("540010", "22960", "JAM MAKING SET", 10, at("09:00"), Decimal("1.0000"), 14002, UK, False),
    ("C540011", "22960", "JAM MAKING SET", -3, at("10:00"), Decimal("1.0000"), 14002, UK, True),
    ("C540012", "22960", "JAM MAKING SET", -10, at("11:00"), Decimal("1.0000"), 14002, UK, True),
    ("540021", "22961", "JAM JAR", 5, at("09:10"), Decimal("2.0000"), 14003, UK, False),
    ("C540022", "22961", "JAM JAR", -2, at("09:30"), Decimal("2.0000"), 14003, UK, True),
    ("540030", "22962", "BOWL", 5, at("08:00"), Decimal("1.5000"), 14004, UK, False),
    ("C540031", "22962", "BOWL", -5, at("12:01"), Decimal("1.5000"), 14004, UK, True),
    ("540050", "22964", "CUP", 5, at("08:00"), Decimal("2.0000"), 14006, UK, False),
    ("C540051", "22964", "CUP", -5, at("08:30"), Decimal("2.5000"), 14006, UK, True),
    ("C540070", "22966", "FORK", -1, at("08:00"), Decimal("6.0000"), 14008, UK, True),
    ("540071", "22966", "FORK", 1, at("09:00"), Decimal("6.0000"), 14008, UK, False),
    ("540080", "22967", "KNIFE", 3, at("08:00"), Decimal("1.2500"), None, UK, False),
    ("C540081", "22967", "KNIFE", -3, at("08:30"), Decimal("1.2500"), None, UK, True),
    ("541001", "22968", "MUG", 1, at("08:00"), Decimal("1.0000"), 15000, UK, False),
]
HEADER = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]


def build_workbook(path, first, second):
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in zip(SHEETS, (first, second)):
        sheet = workbook.create_sheet(name)
        sheet.append(HEADER)
        for _, row in rows:
            sheet.append(list(row))
    workbook.save(path)


@pytest.fixture
def connect():
    def open_connection():
        return psycopg.connect()

    with open_connection() as connection:
        connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    yield open_connection
    with open_connection() as connection:
        connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")


def table_rows(connect):
    with connect() as connection:
        return sorted(connection.execute(f"SELECT * FROM {TABLE}").fetchall(), key=repr)


def test_pipeline_end_to_end(tmp_path, connect):
    workbook = tmp_path / "book.xlsx"
    parquet = tmp_path / "out.parquet"
    build_workbook(workbook, FIRST, SECOND)

    report = pipeline.run(workbook, parquet, connect)

    tags = [tag for tag, _ in FIRST + SECOND]
    expected_outcomes = {tag: tags.count(tag) for tag in set(tags)}
    assert report["raw_rows"] == len(tags)
    assert report["outcomes"] == expected_outcomes
    assert sum(report["outcomes"].values()) == len(tags)
    assert report["loaded_rows"] == len(EXPECTED)
    assert report["checks"] == {"rows": len(EXPECTED), "null_free": True, "duplicate_free": True}
    table = pq.read_table(parquet)
    assert table.column_names == [
        "invoice", "stock_code", "description", "quantity", "invoice_date",
        "price", "customer_id", "country", "is_cancellation",
    ]
    assert [tuple(row.values()) for row in table.to_pylist()] == EXPECTED
    assert table_rows(connect) == sorted(EXPECTED, key=repr)

    pipeline.run(workbook, parquet, connect)
    assert table_rows(connect) == sorted(EXPECTED, key=repr)


def test_failed_check_keeps_previous_contents(tmp_path, connect, monkeypatch):
    workbook = tmp_path / "book.xlsx"
    build_workbook(workbook, FIRST, SECOND)
    pipeline.run(workbook, tmp_path / "first.parquet", connect)

    smaller = tmp_path / "small.xlsx"
    build_workbook(smaller, FIRST[:1], [])
    write = pipeline.write_parquet
    monkeypatch.setattr(pipeline, "write_parquet", lambda rows, path: write(rows + rows, path))

    with pytest.raises(StepError) as raised:
        pipeline.run(smaller, tmp_path / "second.parquet", connect)

    assert raised.value.step == "check"
    assert "repeat exactly" in str(raised.value)
    assert table_rows(connect) == sorted(EXPECTED, key=repr)


def test_failure_logs_one_line_naming_the_step(tmp_path, connect, caplog):
    workbook = tmp_path / "book.xlsx"
    build_workbook(workbook, [r("x", "536001", "WHAT-IS-THIS", "?", 1, "08:00", 1.0, 1)], [])

    with pytest.raises(StepError) as raised:
        pipeline.run(workbook, tmp_path / "out.parquet", connect)

    assert raised.value.step == "clean"
    lines = [record.getMessage() for record in caplog.records if record.levelname == "ERROR"]
    assert len(lines) == 1
    assert lines[0].startswith("ETL step clean failed:") and "WHAT-IS-THIS" in lines[0]
    assert "\n" not in lines[0]


def test_overlap_compares_rows_as_read_before_trimming():
    first = r("x", "536004", "84406B", "CREAM CUPID", 8, "08:15", 2.75, 13047)[1]
    second = r("x", "536004", "84406B", "CREAM CUPID ", 8, "08:15", 2.75, 13047)[1]
    kept, outcomes = clean([first], [second])
    assert outcomes == {"sale": 2}
    assert [row[2] for row in kept] == ["CREAM CUPID", "CREAM CUPID"]


def test_row_that_is_neither_sale_nor_cancellation_fails():
    row = r("x", "C536001", "85123A", "X", 1, "08:00", 1.0, 1)[1]
    with pytest.raises(ValueError, match="neither a sale nor a cancellation"):
        clean([row], [])
