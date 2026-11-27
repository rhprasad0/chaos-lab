import re
from datetime import datetime
from decimal import Decimal

from openpyxl import load_workbook

from .config import SHEETS

TRAILING_ZERO = re.compile(r"^(\d+)\.0+$")


def _text(value):
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, str):
        match = TRAILING_ZERO.match(value)
        return match.group(1) if match else value
    return str(value)


def _integer(value):
    if value is None or value == "":
        return None
    return int(float(value))


def _decimal(value):
    return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)


def _timestamp(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def read_workbook(path):
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheets = []
    for name in SHEETS:
        if name not in workbook.sheetnames:
            raise ValueError(f"workbook has no sheet {name!r}")
        rows = workbook[name].iter_rows(min_row=2, max_col=8, values_only=True)
        sheet = []
        for number, cells in enumerate(rows, start=2):
            if all(cell is None for cell in cells):
                continue
            try:
                invoice, stock, description, quantity, date, price, customer, country = cells
                sheet.append(
                    (
                        _text(invoice),
                        _text(stock),
                        description,
                        _integer(quantity),
                        _timestamp(date),
                        _decimal(price),
                        _integer(customer),
                        country,
                    )
                )
            except (TypeError, ValueError, ArithmeticError) as error:
                raise ValueError(f"sheet {name!r} row {number}: {error}") from error
        sheets.append(sheet)
    workbook.close()
    return sheets
