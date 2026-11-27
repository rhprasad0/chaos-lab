import re
from datetime import datetime
from decimal import Decimal

import openpyxl

SHEETS = ("Year 2009-2010", "Year 2010-2011")
HEADER = ("Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country")
TRAILING_ZERO = re.compile(r"(\d+)\.0")


class ExtractError(Exception):
    pass


def _text(value):
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, str) and TRAILING_ZERO.fullmatch(value):
        return value[:-2]
    return str(value)


def _integer(value, where):
    if isinstance(value, str) and TRAILING_ZERO.fullmatch(value.strip()):
        value = value.strip()[:-2]
    try:
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(value)
        return int(value)
    except (TypeError, ValueError):
        raise ExtractError(f"{where}: {value!r} is not an integer") from None


def _row(raw, where):
    invoice, stock_code, description, quantity, invoice_date, price, customer_id, country = raw
    if not isinstance(invoice_date, datetime):
        raise ExtractError(f"{where}: invoice date {invoice_date!r} is not a date")
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        raise ExtractError(f"{where}: price {price!r} is not a number")
    if invoice is None or stock_code is None:
        raise ExtractError(f"{where}: missing invoice or stock code")
    customer = None if customer_id in (None, "") else _integer(customer_id, where)
    return (
        _text(invoice),
        _text(stock_code),
        _text(description),
        _integer(quantity, where),
        invoice_date,
        Decimal(repr(price)),
        customer,
        _text(country),
    )


def read_workbook(path):
    workbook = openpyxl.load_workbook(path, read_only=True)
    try:
        missing = [name for name in SHEETS if name not in workbook.sheetnames]
        if missing:
            raise ExtractError(f"workbook has no sheet {missing}; found {workbook.sheetnames}")
        sheets = []
        for name in SHEETS:
            rows = workbook[name].iter_rows(values_only=True)
            header = next(rows, None)
            if tuple(header or ())[:8] != HEADER:
                raise ExtractError(f"sheet {name!r} header is {header!r}, expected {HEADER!r}")
            sheets.append(
                [
                    _row(raw, f"sheet {name!r} row {number}")
                    for number, raw in enumerate(rows, start=2)
                    if any(cell is not None for cell in raw)
                ]
            )
        return sheets
    finally:
        workbook.close()
