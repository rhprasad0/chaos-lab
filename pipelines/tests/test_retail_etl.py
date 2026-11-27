import logging
from datetime import datetime
from decimal import Decimal

import openpyxl
import psycopg
import pyarrow.parquet as pq
import pytest
from psycopg import sql

from retail_etl import load
from retail_etl.load import CheckError, check
from retail_etl.pipeline import StepError, run

SCHEMA = "trial_issue_test"
HEADER = ("Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country")


def at(hour, minute=0, day=1):
    return datetime(2010, 12, day, hour, minute)


UK = "United Kingdom"
HEART = (10001, "85123A", "  HEART   HOLDER ", 6, at(8), 2.55, 17850.0, UK)
LANTERN = (10002, 71053.0, "LANTERN", 4, at(8, 5), 3.39, 17850, UK)
REGENCY = ("10003", "22423", "REGENCY", 1, at(9), 12.75, "12583", UK)
DUPLICATE_IN_SECOND = (10027, "21218", None, 2, at(13), 0.85, 30000, "France")

FIRST_SHEET = [
    HEART,
    LANTERN,
    LANTERN,
    REGENCY,
    (10004, "TEST001", "test", 1, at(9, 1), 1.0, 1, UK),
    ("A10005", "85123A", "Adjust bad debt", 1, at(9, 2), -100.0, None, UK),
    (10006, "B", "Adjust bad debt", 1, at(9, 3), 5.0, None, UK),
    (10007, "22666", "damaged", -5, at(9, 4), 0, None, UK),
    (10008, "22667", "gift", 1, at(9, 5), 0, 14000, UK),
    (10009, "POST", "POSTAGE", 1, at(9, 6), 18.0, 12583, UK),
    (10029, " bank charges ", "Bank Charges", 1, at(9, 7), 15.0, 12583, UK),
    (10030, "GIFT_0001_20", "Dotcomgiftshop Gift Voucher", 1, at(9, 8), 16.67, 12583, UK),
    (10010, "84406b", "COAT HANGER", 8, at(10), 2.75, 20000, UK),
    ("C10011", "84406B", "COAT HANGER", -8, at(11), 2.75, 20000, UK),
    (10012, "21212", "PACK OF CAKE CASES", 10, at(9), 1.25, 20001, UK),
    ("C10013", "21212", "PACK OF CAKE CASES", -4, at(9, 30), 1.25, 20001, UK),
    ("C10014", "21212", "PACK OF CAKE CASES", -10, at(10), 1.25, 20001, UK),
    (10015, "21213", "BOWL", 3, at(6), 1.0, 20002, UK),
    ("C10016", "21213", "BOWL", -3, at(10, 1), 1.0, 20002, UK),
    (10031, "21219", "JAR", 2, at(7), 1.0, 20003, UK),
    ("C10032", "21219", "JAR", -2, at(7, 30), 1.5, 20003, UK),
    (10017, "21214", "MUG", 5, at(9), 2.0, 20004, UK),
    (10018, "21214", "MUG", 5, at(10), 2.0, 20004, UK),
    ("C10019", "21214", "MUG", -5, at(10, 30), 2.0, 20004, UK),
    ("C10021", "21215", "PLATE", -1, at(12), 3.0, 20005, UK),
    (10020, "21215", "PLATE", 1, at(12), 3.0, 20005, UK),
    (10023, "21216", "TRAY", 2, at(12), 4.0, None, UK),
    ("C10022", "21216", "TRAY", -2, at(13), 4.0, None, UK),
    (10025, "21217", "SPOON", 3, at(8), 1.0, 20006, UK),
    ("C10026", "21217", "SPOON", -7, at(8, 10), 1.0, 20006, UK),
    (10033, "85048", "   ", 1, at(14), 6.95, 13085, UK),
    (10034, 22750.0, None, 1, at(14, 5), 1.0, "13086.0", UK),
]
SECOND_SHEET = [
    LANTERN,
    LANTERN,
    LANTERN,
    REGENCY,
    (10040, "SP1002", "SPARE", 1, at(15), 1.5, 15000, "Spain"),
    (10041, "DCGS0004", "DOTCOM", 1, at(15, 1), 9.99, 15000, "Spain"),
    DUPLICATE_IN_SECOND,
    DUPLICATE_IN_SECOND,
]

EXPECTED = [
    ("10001", "85123A", "HEART HOLDER", 6, at(8), "2.550", 17850, UK, False),
    ("10002", "71053", "LANTERN", 4, at(8, 5), "3.390", 17850, UK, False),
    ("10003", "22423", "REGENCY", 1, at(9), "12.750", 12583, UK, False),
    ("10012", "21212", "PACK OF CAKE CASES", 10, at(9), "1.250", 20001, UK, False),
    ("C10013", "21212", "PACK OF CAKE CASES", -4, at(9, 30), "1.250", 20001, UK, True),
    ("C10014", "21212", "PACK OF CAKE CASES", -10, at(10), "1.250", 20001, UK, True),
    ("10015", "21213", "BOWL", 3, at(6), "1.000", 20002, UK, False),
    ("C10016", "21213", "BOWL", -3, at(10, 1), "1.000", 20002, UK, True),
    ("10031", "21219", "JAR", 2, at(7), "1.000", 20003, UK, False),
    ("C10032", "21219", "JAR", -2, at(7, 30), "1.500", 20003, UK, True),
    ("10017", "21214", "MUG", 5, at(9), "2.000", 20004, UK, False),
    ("10023", "21216", "TRAY", 2, at(12), "4.000", None, UK, False),
    ("C10022", "21216", "TRAY", -2, at(13), "4.000", None, UK, True),
    ("10025", "21217", "SPOON", 3, at(8), "1.000", 20006, UK, False),
    ("C10026", "21217", "SPOON", -7, at(8, 10), "1.000", 20006, UK, True),
    ("10033", "85048", None, 1, at(14), "6.950", 13085, UK, False),
    ("10034", "22750", None, 1, at(14, 5), "1.000", 13086, UK, False),
    ("10040", "SP1002", "SPARE", 1, at(15), "1.500", 15000, "Spain", False),
    ("10041", "DCGS0004", "DOTCOM", 1, at(15, 1), "9.990", 15000, "Spain", False),
    ("10027", "21218", None, 2, at(13), "0.850", 30000, "France", False),
]
EXPECTED_OUTCOMES = {
    "sheet_overlap": 3,
    "duplicate": 3,
    "test": 1,
    "bad_debt": 2,
    "stock_adjustment": 1,
    "free_item": 1,
    "non_merchandise": 3,
    "void_sale": 3,
    "void_cancellation": 3,
    "sale": 14,
    "return": 6,
}


def build_workbook(path, first=FIRST_SHEET, second=SECOND_SHEET):
    workbook = openpyxl.Workbook()
    for sheet, (title, rows) in zip(
        (workbook.active, workbook.create_sheet()), (("Year 2009-2010", first), ("Year 2010-2011", second))
    ):
        sheet.title = title
        sheet.append(HEADER)
        for row in rows:
            sheet.append(row)
    workbook.save(path)


@pytest.fixture
def connect():
    def connect():
        return psycopg.connect()

    yield connect
    with connect() as connection:
        connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")


def table_rows(connect):
    with connect() as connection:
        return connection.execute(
            f"SELECT invoice, stock_code, description, quantity, invoice_date, price::text, customer_id, "
            f"country, is_cancellation FROM {SCHEMA}.transactions"
        ).fetchall()


def run_local(tmp_path, connect, first=FIRST_SHEET, second=SECOND_SHEET):
    source = tmp_path / "workbook.xlsx"
    target = tmp_path / "out.parquet"
    build_workbook(source, first, second)
    return run(str(source), str(target), SCHEMA, connect, str(tmp_path)), target


def test_pipeline_end_to_end(tmp_path, connect):
    result, target = run_local(tmp_path, connect)

    assert result == {"rows": len(EXPECTED), "outcomes": EXPECTED_OUTCOMES}
    assert sorted(table_rows(connect)) == sorted(EXPECTED)
    parquet = pq.read_table(target)
    assert parquet.column_names == [
        "invoice",
        "stock_code",
        "description",
        "quantity",
        "invoice_date",
        "price",
        "customer_id",
        "country",
        "is_cancellation",
    ]
    parquet_rows = [
        (*row[:5], str(row[5]), *row[6:]) for row in zip(*(parquet.column(i).to_pylist() for i in range(9)))
    ]
    assert sorted(parquet_rows) == sorted(EXPECTED)
    assert isinstance(parquet.column("price").to_pylist()[0], Decimal)


def test_rerun_replaces_the_table(tmp_path, connect):
    run_local(tmp_path, connect)
    run_local(tmp_path, connect)

    assert len(table_rows(connect)) == len(EXPECTED)


def test_failing_check_keeps_previous_contents(tmp_path, connect, monkeypatch, caplog):
    run_local(tmp_path, connect)
    before = sorted(table_rows(connect))

    original = load.check
    monkeypatch.setattr(load, "check", lambda cursor, table, expected: original(cursor, table, expected + 1))
    with caplog.at_level(logging.ERROR), pytest.raises(StepError, match="step check failed"):
        run_local(tmp_path, connect)

    assert sorted(table_rows(connect)) == before
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR] == [
        "ETL step check failed: CheckError: table has 20 rows but the parquet has 21"
    ]


def test_check_rejects_null_and_duplicate_rows(connect):
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(f"CREATE SCHEMA {SCHEMA}")
        cursor.execute(
            f"CREATE TABLE {SCHEMA}.t (invoice text, stock_code text, description text, quantity integer, "
            "invoice_date timestamp, price numeric, customer_id integer, country text, is_cancellation boolean)"
        )
        cursor.execute(f"INSERT INTO {SCHEMA}.t VALUES ('1','A',NULL,1,now(),1,NULL,'x',false)")
        cursor.execute(f"INSERT INTO {SCHEMA}.t VALUES ('1','A',NULL,1,now(),1,NULL,'x',false)")
        with pytest.raises(CheckError, match="duplicate"):
            check(cursor, sql.Identifier(SCHEMA, "t"), 2)
        cursor.execute(f"UPDATE {SCHEMA}.t SET price = NULL")
        with pytest.raises(CheckError, match="NULL price"):
            check(cursor, sql.Identifier(SCHEMA, "t"), 2)
        with pytest.raises(CheckError, match="2 rows but the parquet has 3"):
            check(cursor, sql.Identifier(SCHEMA, "t"), 3)


def test_unrecognised_stock_code_fails_the_run(tmp_path, connect):
    odd = (10050, "WHATEVER", "odd", 1, at(16), 1.0, 1, UK)
    with pytest.raises(StepError, match="step clean failed: CleaningError: unrecognised stock code 'WHATEVER'"):
        run_local(tmp_path, connect, first=[odd])


def test_row_that_is_neither_sale_nor_cancellation_fails_the_run(tmp_path, connect):
    odd = (10051, "21212", "odd", -1, at(16), 1.0, 1, UK)
    with pytest.raises(StepError, match="step clean failed: CleaningError: invoice 10051"):
        run_local(tmp_path, connect, first=[odd])
