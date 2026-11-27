import logging
from datetime import datetime
from decimal import Decimal

import psycopg
import pyarrow.parquet as pq
import pytest
from openpyxl import Workbook

from retail_etl import handler
from retail_etl.transform import HEADER, SCHEMA, clean, write_parquet

UK = "United Kingdom"


def at(month, day, hour=9, minute=0):
    return datetime(2010, month, day, hour, minute)


def row(invoice, stock, description, quantity, when, price, customer, country=UK):
    return (invoice, stock, description, quantity, when, price, customer, country)


def make_workbook(path, first, second):
    workbook = Workbook()
    for name, rows in (("Year 2009-2010", first), ("Year 2010-2011", second)):
        sheet = workbook.create_sheet(name) if workbook.active.title != "Sheet" else workbook.active
        sheet.title = name
        sheet.append(HEADER)
        for values in rows:
            sheet.append(values)
    workbook.save(path)


@pytest.fixture
def connect():
    def open_connection():
        return psycopg.connect("")

    with open_connection() as connection:
        connection.execute(f"DROP SCHEMA IF EXISTS {handler.SCHEMA} CASCADE")
    return open_connection


def table_rows(connect):
    with connect() as connection:
        return connection.execute(
            f"SELECT * FROM {handler.SCHEMA}.transactions ORDER BY invoice, stock_code, quantity, invoice_date"
        ).fetchall()


DUP = row(10002, 21730, "GLASS STAR", 4, at(12, 2), 4.25, 222.0)
SECOND_ONLY_DUP = row(20001, "21212", "PACK OF 72", 24, at(12, 3), 0.55, 223)

FIRST = [
    row(10001, "85123A", "  WHITE   HANGER ", 6, at(1, 4), 2.55, 111.0),
    row("10001", "85123a", "WHITE HANGER", 2, at(1, 4, 9, 5), 2.55, "111"),
    DUP,
    DUP,
    row(10010, "TEST001", "test", 1, at(1, 5), 1.0, None),
    row(10011, "TEST002", "test", 1, at(1, 5), 1.0, 5),
    row("A563185", "B", "Adjust bad debt", 1, at(1, 5), -11062.06, None),
    row(10012, "B", "Bad", 1, at(1, 5), 3.0, 9),
    row(10013, "22139", "adjusted", -5, at(1, 6), 0, None),
    row(10014, "22139.0", "gift", 1, at(1, 6), 0, 333),
    row(10015, "POST", "POSTAGE", 1, at(1, 6), 18.0, 111),
    row(10016, "dot", "DOTCOM POSTAGE", 1, at(1, 6), 50.0, None),
    row(10017, " gift_0001_20 ", "voucher", 1, at(1, 6), 8.33, 111),
    row(10018, "BANK CHARGES", "fee", 1, at(1, 6), 15.0, 111),
    row(10019, "DCGS0069", "OOH LA LA DOGS COLLAR", 1, at(1, 6), 15.95, None),
    row(10020, 22423, "REGENCY CAKESTAND", 2, at(1, 7), 12.75, 444),
    row("C10021", 22423, "REGENCY CAKESTAND", -2, at(1, 7, 10, 30), 12.75, 444),
    row(10030, "20725", "LUNCH BAG", 10, at(1, 8), 1.65, 555),
    row("C10031", "20725", "LUNCH BAG", -4, at(1, 8, 9, 30), 1.65, 555),
    row("C10032", "20725", "LUNCH BAG", -10, at(1, 8, 10), 1.65, 555),
    row(10040, "84029G", "HOT WATER BOTTLE", 3, at(1, 9), 5.0, 666),
    row("C10041", "84029G", "HOT WATER BOTTLE", -3, at(1, 9, 13, 1), 5.0, 666),
    row(10042, "84029G", "HOT WATER BOTTLE", 3, at(1, 10), 5.0, 667),
    row("C10043", "84029G", "HOT WATER BOTTLE", -3, at(1, 10, 13, 0), 5.0, 667),
    row("C10050", "22960", "JAM MAKING SET", -1, at(1, 11), 3.0, None),
    row("C10051", "22960", "JAM MAKING SET", -1, at(1, 11), 3.0, 700),
    row("C10060", "22961", "JAM JAR", -1, at(1, 12), 1.45, 668),
    row(10060, "22961", "JAM JAR", 1, at(1, 12), 1.45, 668),
    row(10070, "22962", "JAM SPOON", 2, at(1, 13), 1.0, 669),
    row(10071, "22962", "JAM SPOON", 2, at(1, 13, 9, 30), 1.0, 669),
    row("C10072", "22962", "JAM SPOON", -2, at(1, 13, 10), 1.0, 669),
    row(10080, "SP1002", "SPECIAL", 1, at(1, 14), 2.0, None),
]
SECOND = [
    DUP,
    DUP,
    DUP,
    SECOND_ONLY_DUP,
    SECOND_ONLY_DUP,
    row(20002, "21213", "   ", 1, at(12, 4), 1.0, None, "France"),
    row(20003, "22423", "REGENCY CAKESTAND", 1, at(12, 5), 12.75, "444.0"),
]

EXPECTED = [
    ("10001", "85123A", "WHITE HANGER", 6, at(1, 4), Decimal("2.55"), 111, UK, False),
    ("10001", "85123A", "WHITE HANGER", 2, at(1, 4, 9, 5), Decimal("2.55"), 111, UK, False),
    ("10002", "21730", "GLASS STAR", 4, at(12, 2), Decimal("4.25"), 222, UK, False),
    ("10019", "DCGS0069", "OOH LA LA DOGS COLLAR", 1, at(1, 6), Decimal("15.95"), None, UK, False),
    ("10030", "20725", "LUNCH BAG", 10, at(1, 8), Decimal("1.65"), 555, UK, False),
    ("C10031", "20725", "LUNCH BAG", -4, at(1, 8, 9, 30), Decimal("1.65"), 555, UK, True),
    ("C10032", "20725", "LUNCH BAG", -10, at(1, 8, 10), Decimal("1.65"), 555, UK, True),
    ("10040", "84029G", "HOT WATER BOTTLE", 3, at(1, 9), Decimal("5.00"), 666, UK, False),
    ("C10041", "84029G", "HOT WATER BOTTLE", -3, at(1, 9, 13, 1), Decimal("5.00"), 666, UK, True),
    ("C10050", "22960", "JAM MAKING SET", -1, at(1, 11), Decimal("3.00"), None, UK, True),
    ("C10051", "22960", "JAM MAKING SET", -1, at(1, 11), Decimal("3.00"), 700, UK, True),
    ("10070", "22962", "JAM SPOON", 2, at(1, 13), Decimal("1.00"), 669, UK, False),
    ("10080", "SP1002", "SPECIAL", 1, at(1, 14), Decimal("2.00"), None, UK, False),
    ("20001", "21212", "PACK OF 72", 24, at(12, 3), Decimal("0.55"), 223, UK, False),
    ("20002", "21213", None, 1, at(12, 4), Decimal("1.00"), None, "France", False),
    ("20003", "22423", "REGENCY CAKESTAND", 1, at(12, 5), Decimal("12.75"), 444, UK, False),
]
EXPECTED_OUTCOMES = {
    "sale": 11,
    "return": 5,
    "overlap": 2,
    "duplicate": 3,
    "test": 2,
    "bad_debt": 2,
    "stock_adjustment": 1,
    "free_item": 1,
    "non_merchandise": 4,
    "void": 8,
}


def test_pipeline_end_to_end(tmp_path, connect):
    workbook = tmp_path / "book.xlsx"
    parquet = tmp_path / "out.parquet"
    make_workbook(workbook, FIRST, SECOND)

    outcomes, loaded = handler.run(workbook, parquet, connect)

    assert dict(outcomes) == EXPECTED_OUTCOMES
    assert sum(outcomes.values()) == len(FIRST) + len(SECOND)
    assert loaded == len(EXPECTED)
    assert pq.read_table(parquet).schema == SCHEMA
    in_file = pq.read_table(parquet).to_pylist()
    assert [tuple(r.values()) for r in in_file] == EXPECTED
    assert table_rows(connect) == sorted(EXPECTED, key=lambda r: (r[0], r[1], r[3], r[4]))


def test_rerun_replaces_rows(tmp_path, connect):
    workbook = tmp_path / "book.xlsx"
    make_workbook(workbook, FIRST, SECOND)
    handler.run(workbook, tmp_path / "a.parquet", connect)
    handler.run(workbook, tmp_path / "b.parquet", connect)
    assert len(table_rows(connect)) == len(EXPECTED)


def test_failed_check_raises_and_keeps_previous_rows(tmp_path, connect, caplog):
    workbook = tmp_path / "book.xlsx"
    make_workbook(workbook, FIRST, SECOND)
    handler.run(workbook, tmp_path / "a.parquet", connect)
    before = table_rows(connect)

    twins = [
        row(30001, "21212", "PACK  OF 72", 1, at(2, 1), 1.0, 1),
        row(30001, "21212", "PACK OF 72", 1, at(2, 1), 1.0, 1),
    ]
    make_workbook(workbook, twins, [])
    with caplog.at_level(logging.ERROR, logger="retail_etl"):
        with pytest.raises(ValueError, match="exact duplicate"):
            handler.run(workbook, tmp_path / "b.parquet", connect)

    assert "etl step=load failed" in caplog.text
    assert table_rows(connect) == before


def test_row_that_is_neither_sale_nor_cancellation_fails():
    with pytest.raises(ValueError, match="neither a sale nor a cancellation"):
        clean([row("40001", "21212", "X", -1, at(2, 1), 1.0, 1)], [])


def test_price_with_too_many_decimals_is_not_written(tmp_path):
    record = dict.fromkeys(SCHEMA.names)
    record["price"] = Decimal("1.00001")
    with pytest.raises(ValueError, match="decimal places"):
        write_parquet([record], tmp_path / "x.parquet")
