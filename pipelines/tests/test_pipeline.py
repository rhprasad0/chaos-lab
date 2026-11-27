import uuid
from datetime import datetime
from decimal import Decimal

import psycopg
import pyarrow.parquet as pq
import pytest
import xlsxwriter

from retail_etl import etl, handler, load

HEADER = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]
DEC = datetime(2010, 12, 1, 8, 26)
SHEET_2009 = [
    [489434.0, 85048.0, "  PADDED GLASS BALL  ", 12.0, datetime(2009, 12, 1, 7, 45), 6.95, 13085.0, " United Kingdom "],
    ["C489449", "22350", "CAT BOWL", -12.0, datetime(2009, 12, 1, 10, 33), 2.55, 16321.0, "Australia"],
    [489459.0, "21212", "", 3.0, datetime(2009, 12, 1, 11, 0), 1.25, "", "France"],
    [489459.0, "21212", "", 3.0, datetime(2009, 12, 1, 11, 0), 1.25, "", "France"],
    ["A563185", "B", "Adjust bad debt", 1.0, datetime(2010, 8, 12, 14, 50), -11062.06, "", "United Kingdom"],
    [536365.0, "85123A", "WHITE HEART", 6.0, DEC, 2.55, 17850.0, "United Kingdom"],
]
SHEET_2010 = [
    [536365.0, "85123A", "WHITE HEART", 6.0, DEC, 2.55, 17850.0, "United Kingdom"],
    [581587.0, "POST", "POSTAGE", 1.0, datetime(2011, 12, 9, 12, 50), 18.0, 12680.0, "France"],
]


def write_workbook(path, sheets):
    book = xlsxwriter.Workbook(str(path), {"default_date_format": "yyyy-mm-dd hh:mm:ss"})
    for name, rows in sheets.items():
        sheet = book.add_worksheet(name)
        for r, row in enumerate([HEADER, *rows]):
            for c, value in enumerate(row):
                if isinstance(value, datetime):
                    sheet.write_datetime(r, c, value)
                elif value is not None:
                    sheet.write(r, c, value)
    book.close()


@pytest.fixture
def dsn():
    name = "etl_" + uuid.uuid4().hex[:8]
    with psycopg.connect("dbname=postgres", autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {name}")
    yield f"dbname={name}"
    with psycopg.connect("dbname=postgres", autocommit=True) as admin:
        admin.execute(f"DROP DATABASE {name} WITH (FORCE)")


@pytest.fixture
def workbook(tmp_path):
    path = tmp_path / "workbook.xlsx"
    write_workbook(path, {"Year 2009-2010": SHEET_2009, "Year 2010-2011": SHEET_2010})
    return path


EXPECTED = [
    ("489434", "85048", "PADDED GLASS BALL", 12, datetime(2009, 12, 1, 7, 45), Decimal("6.9500"), 13085, "United Kingdom", False),
    ("489459", "21212", None, 3, datetime(2009, 12, 1, 11, 0), Decimal("1.2500"), None, "France", False),
    ("536365", "85123A", "WHITE HEART", 6, DEC, Decimal("2.5500"), 17850, "United Kingdom", False),
    ("581587", "POST", "POSTAGE", 1, datetime(2011, 12, 9, 12, 50), Decimal("18.0000"), 12680, "France", False),
    ("C489449", "22350", "CAT BOWL", -12, datetime(2009, 12, 1, 10, 33), Decimal("2.5500"), 16321, "Australia", True),
]


def table_rows(dsn):
    with psycopg.connect(dsn) as conn:
        return conn.execute("SELECT * FROM retail.transactions ORDER BY invoice, stock_code").fetchall()


def test_pipeline_end_to_end(tmp_path, workbook, dsn):
    parquet = tmp_path / "clean.parquet"
    summary = handler.run(str(workbook), str(parquet), dsn)

    assert table_rows(dsn) == EXPECTED
    rows = pq.read_table(parquet).to_pylist()
    assert sorted(tuple(r.values()) for r in rows) == EXPECTED
    assert summary["extracted"] == 8
    assert summary["dropped_duplicates"] == 2
    assert summary["dropped_negative_price"] == 1
    assert summary["cleaned"] == 5
    assert summary["checks"]["table_rows"] == 5


def test_rerun_replaces_rows(tmp_path, workbook, dsn):
    for _ in range(2):
        handler.run(str(workbook), str(tmp_path / "clean.parquet"), dsn)
    assert table_rows(dsn) == EXPECTED


def test_failing_check_raises_and_keeps_previous_rows(tmp_path, workbook, dsn):
    handler.run(str(workbook), str(tmp_path / "clean.parquet"), dsn)
    etl.write_parquet([EXPECTED[0], EXPECTED[0]], tmp_path / "bad.parquet")

    with pytest.raises(load.CheckError, match="1 exact duplicate rows"):
        load.load(str(tmp_path / "bad.parquet"), dsn)

    assert table_rows(dsn) == EXPECTED


def test_failure_is_logged_with_step_and_raised(tmp_path, dsn, caplog):
    with pytest.raises(Exception):
        handler.run(str(tmp_path / "missing.xlsx"), str(tmp_path / "clean.parquet"), dsn)
    assert any(r.message.startswith("step=extract failed:") for r in caplog.records)
