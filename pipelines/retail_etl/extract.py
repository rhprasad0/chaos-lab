import re
from datetime import datetime
from decimal import Decimal

import openpyxl

SHEETS = ("Year 2009-2010", "Year 2010-2011")
_INTEGRAL = re.compile(r"^-?\d+\.0+$")


def _text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value)
    return text[:-2] if _INTEGRAL.match(text.strip()) and text.endswith(".0") else text


def _int(value):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return int(float(value))


def _timestamp(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip())


def read_sheet(worksheet):
    rows = worksheet.iter_rows(min_row=2, values_only=True)
    for number, cells in enumerate(rows, start=2):
        invoice, stock_code, description, quantity, invoice_date, price, customer_id, country = cells[:8]
        yield (
            _text(invoice),
            _text(stock_code),
            None if description is None else str(description),
            _int(quantity),
            _timestamp(invoice_date),
            Decimal(str(price)),
            _int(customer_id),
            None if country is None else str(country),
        )


def extract(path):
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return [list(read_sheet(workbook[name])) for name in SHEETS]
    finally:
        workbook.close()
