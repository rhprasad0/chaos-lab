from datetime import datetime
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
from python_calamine import CalamineWorkbook

COLUMNS = (
    "invoice",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "price",
    "customer_id",
    "country",
)
REQUIRED = ("invoice", "stock_code", "quantity", "invoice_date", "price")
SCHEMA = pa.schema(
    [
        ("invoice", pa.string()),
        ("stock_code", pa.string()),
        ("description", pa.string()),
        ("quantity", pa.int32()),
        ("invoice_date", pa.timestamp("us")),
        ("price", pa.decimal128(12, 4)),
        ("customer_id", pa.int32()),
        ("country", pa.string()),
        ("is_cancellation", pa.bool_()),
    ]
)


SOURCE_COLUMNS = (
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
    "Country",
)


def extract(path):
    workbook = CalamineWorkbook.from_path(path)
    sheets = {}
    for name in workbook.sheet_names:
        header, *rows = workbook.get_sheet_by_name(name).to_python(skip_empty_area=False)
        if tuple(header) != SOURCE_COLUMNS:
            raise ValueError(f"sheet {name!r} has columns {header}, expected {list(SOURCE_COLUMNS)}")
        sheets[name] = rows
    return sheets


def text(value):
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip() or None


def whole_number(value):
    value = text(value)
    return None if value is None else int(float(value))


def clean_row(raw):
    invoice, stock_code, description, quantity, invoice_date, price, customer_id, country = raw
    if isinstance(invoice_date, str):
        invoice_date = datetime.fromisoformat(invoice_date.strip()) if invoice_date.strip() else None
    price = text(price)
    return (
        text(invoice),
        text(stock_code),
        text(description),
        whole_number(quantity),
        invoice_date,
        None if price is None else Decimal(price).quantize(Decimal("0.0001")),
        whole_number(customer_id),
        text(country),
    )


def clean(sheets):
    counts = {"extracted": sum(len(rows) for rows in sheets.values())}
    seen = set()
    kept = []
    missing_required = negative_price = duplicates = 0
    for rows in sheets.values():
        for raw in rows:
            row = clean_row(raw)
            if any(row[COLUMNS.index(name)] is None for name in REQUIRED):
                missing_required += 1
            elif row[5] < 0:
                negative_price += 1
            elif row in seen:
                duplicates += 1
            else:
                seen.add(row)
                kept.append(row + (row[0].startswith("C"),))
    counts.update(
        dropped_missing_required=missing_required,
        dropped_negative_price=negative_price,
        dropped_duplicates=duplicates,
        cleaned=len(kept),
    )
    return kept, counts


def write_parquet(rows, path):
    columns = list(zip(*rows)) if rows else [()] * len(SCHEMA)
    table = pa.Table.from_arrays(
        [pa.array(column, type=field.type) for column, field in zip(columns, SCHEMA)],
        schema=SCHEMA,
    )
    pq.write_table(table, path)
