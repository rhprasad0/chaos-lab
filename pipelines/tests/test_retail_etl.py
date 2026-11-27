import logging
from datetime import datetime
from decimal import Decimal

import openpyxl
import psycopg
import pyarrow.parquet as pq
import pytest

from retail_etl.clean import CleanError, clean
from retail_etl.handler import handler
from retail_etl.load import COLUMNS, CheckError, load, write_parquet
from retail_etl.pipeline import StepError, run

SCHEMA = "trial_issue_test"
CONNINFO = "dbname=postgres"
HEADER = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]
UK = "United Kingdom"


def at(day, hour, minute=0, month=12, year=2010):
    return datetime(year, month, day, hour, minute)


def raw(invoice, stock, quantity, when, price, customer, description="ITEM", country=UK):
    return [invoice, stock, description, quantity, when, price, customer, country]


OVERLAP_SALE = raw("1001", "85123A", 2, at(5, 10), 2.5, 100, "  WHITE  HEART ")
OVERLAP_TEST = raw("1002", "TEST001", 1, at(5, 10), 1.0, 100)
DUPLICATE_IN_SECOND = raw("9001", "85123A", 1, at(5, 11, month=1, year=2011), 3.0, 100)

SHEET_1 = [
    OVERLAP_SALE,
    OVERLAP_SALE,
    OVERLAP_TEST,
    raw("A1003", "85123A", 1, at(5, 10), -5.0, None),
    raw("1004", "B", 1, at(5, 10), 3.0, None),
    raw("1005", "85123A", 1, at(5, 10), 0, None),
    raw("1006", "85123A", 1, at(5, 10), 0, 100),
    raw("1007", "POST", 1, at(5, 10), 18.0, 100),
    raw("1008", " gift_0001_20 ", 1, at(5, 10), 10.0, 100),
    raw("1009", "84797a ", 3, at(5, 10), 1.25, None, "   ", "France"),
    raw(1010, 21730.0, 1, at(5, 10), 4.95, 101.0, "GLASS", UK),
    raw("1011", "DCGS0001", 1, at(5, 10), 10.0, 102),
    raw("1012", "SP1234", 1, at(5, 10), 10.0, 102),
    raw("2001", "21000", 5, at(6, 10), 1.0, 200),
    raw("C2002", "21000", -5, at(6, 13, 59), 1.0, 200),
    raw("2003", "21001", 5, at(6, 10), 1.0, 201),
    raw("C2004", "21001", -5, at(6, 14), 1.0, 201),
    raw("2005", "21002", 5, at(6, 10), 1.0, 202),
    raw("C2006", "21002", -5, at(6, 14, 1), 1.0, 202),
    raw("2007", "21004", 5, at(6, 10), 1.0, 203),
    raw("C2008", "21004", -5, at(6, 11), 1.5, 203),
    raw("C2010", "21003", -3, at(6, 10), 2.0, 204),
    raw("2009", "21003", 3, at(6, 10), 2.0, 204),
    raw("3001", "22000", 10, at(7, 9), 2.0, 300),
    raw("C3002", "22000", -4, at(7, 9, 30), 2.0, 300),
    raw("C3003", "22000", -10, at(7, 10), 2.0, 300),
    raw("5001", "23000", 3, at(7, 8), 1.0, 500),
    raw("5002", "23000", 3, at(7, 9), 1.0, 500),
    raw("C5003", "23000", -3, at(7, 9, 30), 1.0, 500),
    raw("C6001", "23001", -2, at(7, 9), 3.0, None),
    raw("C7001", "23002", -1, at(7, 9), 1.0, 700),
    raw("6002", "24000", 4, at(8, 8), 1.0, 600),
    raw("6003", "24000", 4, at(8, 8, 30), 1.0, 600),
    raw("C6004", "24000", -6, at(8, 9), 1.0, 600),
    raw("C6005", "24000", -4, at(8, 9, 30), 1.0, 600),
    raw("8001", "25000", 2, at(8, 8), 1.0, 800),
    raw("8002", "25000", 5, at(8, 8, 10), 1.0, 800),
    raw("C8003", "25000", -2, at(8, 8, 20), 1.0, 800),
    raw("C8004", "25000", -5, at(8, 8, 30), 1.0, 800),
]
SHEET_2 = [OVERLAP_SALE, OVERLAP_SALE, OVERLAP_SALE, OVERLAP_TEST, DUPLICATE_IN_SECOND, DUPLICATE_IN_SECOND]

KEPT_INVOICES = {
    "1001", "1009", "1010", "1011", "1012", "9001", "2005", "C2006", "2007", "C2008", "3001", "C3002",
    "C3003", "5001", "C6001", "C7001", "6002", "6003", "C6004", "C6005",
}
SPECIAL = {
    "1001": ("1001", "85123A", "WHITE HEART", 2, at(5, 10), Decimal("2.5"), 100, UK, False),
    "1009": ("1009", "84797A", None, 3, at(5, 10), Decimal("1.25"), None, "France", False),
    "1010": ("1010", "21730", "GLASS", 1, at(5, 10), Decimal("4.95"), 101, UK, False),
}
EXPECTED_COUNTS = {
    "raw": len(SHEET_1) + len(SHEET_2),
    "overlap": 3,
    "duplicate": 3,
    "test": 1,
    "bad_debt": 2,
    "stock_adjustment": 1,
    "free_item": 1,
    "non_merchandise": 2,
    "void_sale": 6,
    "void_cancellation": 6,
    "sale": 12,
    "return": 8,
    "kept": 20,
}


def expected_rows():
    rows = {}
    for row in SHEET_1 + SHEET_2:
        invoice = str(row[0])
        if invoice in KEPT_INVOICES:
            rows[invoice] = SPECIAL.get(
                invoice,
                (invoice, row[1], row[2], row[3], row[4], Decimal(str(row[5])), row[6], row[7], invoice.startswith("C")),
            )
    return sorted(rows.values(), key=lambda r: (r[0], r[1]))


def write_workbook(path, sheet_1=SHEET_1, sheet_2=SHEET_2):
    workbook = openpyxl.Workbook()
    for sheet, rows in zip((workbook.active, workbook.create_sheet()), (sheet_1, sheet_2)):
        sheet.append(HEADER)
        for row in rows:
            sheet.append(row)
    workbook.worksheets[0].title = "Year 2009-2010"
    workbook.worksheets[1].title = "Year 2010-2011"
    workbook.save(path)


@pytest.fixture
def database():
    def drop():
        with psycopg.connect(CONNINFO, autocommit=True) as conn:
            conn.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")

    drop()
    yield
    drop()


def table_rows():
    with psycopg.connect(CONNINFO) as conn:
        rows = conn.execute(
            f"SELECT {', '.join(COLUMNS)} FROM {SCHEMA}.transactions ORDER BY invoice, stock_code"
        ).fetchall()
    return [tuple(r) for r in rows]


def parquet_rows(path):
    table = pq.read_table(path)
    rows = list(zip(*(table.column(name).to_pylist() for name in COLUMNS)))
    return sorted(rows, key=lambda r: (r[0], r[1]))


def test_pipeline_end_to_end(tmp_path, database):
    workbook = tmp_path / "in.xlsx"
    output = tmp_path / "out.parquet"
    write_workbook(workbook)

    result = run(str(workbook), str(output), CONNINFO, SCHEMA)

    assert result["counts"] == EXPECTED_COUNTS
    assert result["loaded_rows"] == 20
    assert result["parquet_bytes"] == output.stat().st_size
    assert table_rows() == expected_rows()
    assert parquet_rows(output) == expected_rows()


def test_rerun_replaces_rows(tmp_path, database):
    workbook = tmp_path / "in.xlsx"
    write_workbook(workbook)
    for _ in range(2):
        run(str(workbook), str(tmp_path / "out.parquet"), CONNINFO, SCHEMA)
    assert table_rows() == expected_rows()


def test_failed_check_keeps_previous_contents(tmp_path, database):
    workbook = tmp_path / "in.xlsx"
    write_workbook(workbook)
    run(str(workbook), str(tmp_path / "out.parquet"), CONNINFO, SCHEMA)
    before = table_rows()

    row = ("X1", "85123A", "D", 1, at(1, 1), Decimal("1"), 1, UK, False)
    bad = tmp_path / "dupes.parquet"
    write_parquet([row, row], bad)
    with pytest.raises(CheckError, match="duplicate"):
        load(CONNINFO, SCHEMA, str(bad))

    assert table_rows() == before


def test_null_in_required_column_fails_check(tmp_path, database):
    row = ("X1", "85123A", "D", 1, at(1, 1), None, 1, UK, False)
    bad = tmp_path / "nulls.parquet"
    write_parquet([row], bad)
    with pytest.raises(CheckError, match="NULL"):
        load(CONNINFO, SCHEMA, str(bad))


@pytest.mark.parametrize(
    "bad_row, message",
    [
        (raw("3000", "WEIRD", 1, at(1, 1), 1.0, 1), "unknown stock code"),
        (raw("3001", "85123A", -1, at(1, 1), 1.0, 1), "neither a sale nor a cancellation"),
        (raw("C3002", "85123A", 1, at(1, 1), 1.0, 1), "neither a sale nor a cancellation"),
    ],
)
def test_unclassifiable_rows_fail_the_run(tmp_path, bad_row, message):
    from retail_etl.extract import read_workbook

    workbook = tmp_path / "in.xlsx"
    write_workbook(workbook, [bad_row], [])
    first, second = read_workbook(str(workbook))
    with pytest.raises(CleanError, match=message):
        clean(first, second)


def test_handler_logs_failed_step_and_raises(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("INPUT_URI", str(tmp_path / "missing.xlsx"))
    monkeypatch.setenv("OUTPUT_URI", str(tmp_path / "out.parquet"))
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_USER", "chaos_lab")
    monkeypatch.setenv("DB_NAME", "chaos_lab")
    monkeypatch.setenv("DB_SCHEMA", SCHEMA)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with caplog.at_level(logging.ERROR), pytest.raises(StepError):
        handler({}, None)
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert "step=extract" in messages[0] and "missing.xlsx" in messages[0]
