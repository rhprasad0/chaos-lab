import os
from datetime import datetime
from decimal import Decimal

import openpyxl
import psycopg
import pyarrow.parquet as pq
import pytest

from pipelines.retail_etl.errors import PipelineError
from pipelines.retail_etl.load import TABLE, load
from pipelines.retail_etl.pipeline import run
from pipelines.retail_etl.write import write_parquet

HEADER = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]
UK = "United Kingdom"


def at(day, hour, minute=0):
    return datetime(2010, 12, day, hour, minute)


SHEET_1 = [
    [500001, 10001, "VOIDED SALE", 10, at(1, 10), 2.5, 1.0, UK],
    ["C500002", "10001", "VOIDED SALE", -10, at(1, 11), 2.5, 1, UK],
    [500003, "10002", "BIG LOT", 10, at(1, 10), 1.0, 1, UK],
    [500004, "10002", "SMALL  LOT", 5, at(1, 10, 30), 1.0, 1, UK],
    ["C500005", "10002", "SMALL LOT", -4, at(1, 12), 1.0, 1, UK],
    ["C500006", "10002", "SMALL LOT", -5, at(1, 12, 30), 1.0, 1, UK],
    [500007, "10003", "LATE RETURN", 3, at(1, 10), 2.0, 2, UK],
    ["C500008", "10003", "LATE RETURN", -3, at(1, 15), 2.0, 2, UK],
    [500009, "10004a ", " tidy\t  description ", 1, at(2, 9), 4.25, 3, "France"],
    [500010, "10005", "   ", 2, at(2, 9), 3.0, None, "France"],
    ["C500011", "10005", "NO CUSTOMER", -1, at(2, 10), 3.0, None, "France"],
    [500012, "10006", "SAME TIME", 2, at(3, 9), 1.5, 4, UK],
    ["C500013", "10006", "SAME TIME", -2, at(3, 9), 1.5, 4, UK],
    [500014, "10007", "OVERLAP", 1, at(4, 9), 1.0, 5, UK],
    [500014, "10007", "OVERLAP", 1, at(4, 9), 1.0, 5, UK],
    [500015, "10008", "REPEAT", 1, at(4, 9), 1.0, 5, UK],
    [500015, "10008", "REPEAT", 1, at(4, 9), 1.0, 5, UK],
    [500016, "TEST001", "TEST", 1, at(5, 9), 1.0, 6, UK],
    [500017, "test002", "TEST", 1, at(5, 9), 1.0, 6, UK],
    ["A500018", "10009", "BAD DEBT", 1, at(5, 9), 1.0, None, UK],
    [500019, "B", "BAD DEBT", 1, at(5, 9), 1.0, None, UK],
    [500020, "10010", "ADJUSTMENT", 1, at(5, 9), 0, None, UK],
    [500021, "10011", "FREE", 1, at(5, 9), 0.0, 7, UK],
    [500022, "POST", "POSTAGE", 1, at(5, 9), 15.0, 7, UK],
    [500023, "gift_0001_20", "VOUCHER", 1, at(5, 9), 20.0, 7, UK],
    [500024, "DCGS0069", "DCGS PRODUCT", 1, at(5, 9), 9.0, 7, UK],
    [500025, "SP1002", "SP PRODUCT", 1, at(5, 9), 9.0, 7, UK],
]
SHEET_2 = [
    [500014, "10007", "OVERLAP", 1, at(4, 9), 1.0, 5, UK],
    [500014, "10007", "OVERLAP", 1, at(4, 9), 1.0, 5, UK],
    [500014, "10007", "OVERLAP", 1, at(4, 9), 1.0, 5, UK],
    [500026, "10012", "SECOND SHEET", 1, at(8, 9), 5.0, 8, UK],
]

EXPECTED_ROWS = [
    ("500003", "10002", "BIG LOT", 10, at(1, 10), Decimal("1.0000"), 1, UK, False),
    ("500004", "10002", "SMALL LOT", 5, at(1, 10, 30), Decimal("1.0000"), 1, UK, False),
    ("C500005", "10002", "SMALL LOT", -4, at(1, 12), Decimal("1.0000"), 1, UK, True),
    ("C500006", "10002", "SMALL LOT", -5, at(1, 12, 30), Decimal("1.0000"), 1, UK, True),
    ("500007", "10003", "LATE RETURN", 3, at(1, 10), Decimal("2.0000"), 2, UK, False),
    ("C500008", "10003", "LATE RETURN", -3, at(1, 15), Decimal("2.0000"), 2, UK, True),
    ("500009", "10004A", "tidy description", 1, at(2, 9), Decimal("4.2500"), 3, "France", False),
    ("500010", "10005", None, 2, at(2, 9), Decimal("3.0000"), None, "France", False),
    ("C500011", "10005", "NO CUSTOMER", -1, at(2, 10), Decimal("3.0000"), None, "France", True),
    ("500014", "10007", "OVERLAP", 1, at(4, 9), Decimal("1.0000"), 5, UK, False),
    ("500015", "10008", "REPEAT", 1, at(4, 9), Decimal("1.0000"), 5, UK, False),
    ("500024", "DCGS0069", "DCGS PRODUCT", 1, at(5, 9), Decimal("9.0000"), 7, UK, False),
    ("500025", "SP1002", "SP PRODUCT", 1, at(5, 9), Decimal("9.0000"), 7, UK, False),
    ("500026", "10012", "SECOND SHEET", 1, at(8, 9), Decimal("5.0000"), 8, UK, False),
]

EXPECTED_OUTCOMES = {
    "sheet_overlap": 2,
    "duplicate": 3,
    "test": 2,
    "bad_debt": 2,
    "stock_adjustment": 1,
    "free_item": 1,
    "non_merchandise": 2,
    "void": 4,
    "sale": 10,
    "return": 4,
}


def workbook(path, sheet_1=SHEET_1, sheet_2=SHEET_2):
    book = openpyxl.Workbook()
    for ws, name, rows in (
        (book.active, "Year 2009-2010", sheet_1),
        (book.create_sheet(), "Year 2010-2011", sheet_2),
    ):
        ws.title = name
        ws.append(HEADER)
        for row in rows:
            ws.append(row)
    book.save(path)


def connect():
    return psycopg.connect(dbname=os.environ.get("PGDATABASE", "postgres"))


@pytest.fixture
def clean_schema():
    with connect() as conn:
        conn.execute("DROP SCHEMA IF EXISTS trial_issue_19 CASCADE")
    yield
    with connect() as conn:
        conn.execute("DROP SCHEMA IF EXISTS trial_issue_19 CASCADE")


def table_rows():
    with connect() as conn:
        return conn.execute(f"SELECT * FROM {TABLE} ORDER BY invoice, stock_code, description").fetchall()


def run_pipeline(tmp_path, sheet_1=SHEET_1, sheet_2=SHEET_2):
    source = tmp_path / "workbook.xlsx"
    workbook(source, sheet_1, sheet_2)
    published = []
    summary = run(connect, lambda: str(source), published.append, str(tmp_path / "out.parquet"))
    return summary, published


def test_pipeline_end_to_end(tmp_path, clean_schema):
    summary, published = run_pipeline(tmp_path)

    expected = [tuple(r) for r in EXPECTED_ROWS]
    assert summary["raw_rows"] == len(SHEET_1) + len(SHEET_2)
    assert summary["outcomes"] == EXPECTED_OUTCOMES
    assert sum(EXPECTED_OUTCOMES.values()) == summary["raw_rows"]
    assert summary["checks"]["rows"] == len(expected)
    assert published == [str(tmp_path / "out.parquet")]

    parquet = pq.read_table(tmp_path / "out.parquet")
    assert parquet.column_names == [
        "invoice", "stock_code", "description", "quantity", "invoice_date",
        "price", "customer_id", "country", "is_cancellation",
    ]
    assert sorted(zip(*(parquet.column(n).to_pylist() for n in parquet.column_names)), key=_key) == sorted(expected, key=_key)
    assert sorted(table_rows(), key=_key) == sorted(expected, key=_key)


def _key(row):
    return (row[0], row[1], row[2] or "")


def test_rerun_replaces_rows(tmp_path, clean_schema):
    run_pipeline(tmp_path)
    run_pipeline(tmp_path)
    assert len(table_rows()) == len(EXPECTED_ROWS)


def test_unknown_stock_code_fails_the_run(tmp_path, clean_schema):
    bad = SHEET_1 + [[500030, "WHAT", "UNKNOWN", 1, at(9, 9), 1.0, 9, UK]]
    with pytest.raises(PipelineError, match="WHAT"):
        run_pipeline(tmp_path, bad)


def test_failed_check_keeps_previous_contents(tmp_path, clean_schema):
    run_pipeline(tmp_path)
    before = table_rows()
    row = ("700001", "20001", "TWICE", 1, at(9, 9), Decimal("1"), 9, UK, False)
    duplicated = tmp_path / "duplicated.parquet"
    write_parquet([row, row], duplicated)

    with pytest.raises(PipelineError, match="duplicate") as caught:
        load(connect, str(duplicated))

    assert caught.value.step == "check"
    assert table_rows() == before


def test_null_in_required_column_fails_check(tmp_path, clean_schema):
    run_pipeline(tmp_path)
    before = table_rows()
    nulled = tmp_path / "nulled.parquet"
    write_parquet([("700001", "20001", None, 1, at(9, 9), None, 9, UK, False)], nulled)

    with pytest.raises(PipelineError, match="price"):
        load(connect, str(nulled))

    assert table_rows() == before
