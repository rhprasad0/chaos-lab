import re
from datetime import datetime
from decimal import Decimal

import openpyxl

SHEETS = ("Year 2009-2010", "Year 2010-2011")
COLUMNS = (
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
    "Country",
)


def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return re.sub(r"\.0$", "", str(value))


def _integer(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return int(Decimal(str(value).strip()))


def _row(cells):
    invoice, code, description, quantity, date, price, customer, country = cells
    if isinstance(date, str):
        date = datetime.fromisoformat(date)
    return (
        _text(invoice),
        _text(code),
        description,
        _integer(quantity),
        date,
        Decimal(repr(price)) if isinstance(price, float) else Decimal(str(price)),
        _integer(customer),
        country,
    )


def extract(path):
    workbook = openpyxl.load_workbook(path, read_only=True)
    sheets = []
    for name in SHEETS:
        rows = workbook[name].iter_rows(values_only=True)
        header = tuple(next(rows))[: len(COLUMNS)]
        if header != COLUMNS:
            raise ValueError(f"sheet {name!r} has columns {header}, expected {COLUMNS}")
        sheets.append([_row(r[: len(COLUMNS)]) for r in rows if any(c is not None for c in r)])
    workbook.close()
    return sheets
