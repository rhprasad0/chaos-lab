from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from .config import SCHEMA, TABLE

COLUMNS = (
    "invoice",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "price",
    "customer_id",
    "country",
    "is_cancellation",
)
PARQUET_SCHEMA = pa.schema(
    [
        ("invoice", pa.string()),
        ("stock_code", pa.string()),
        ("description", pa.string()),
        ("quantity", pa.int32()),
        ("invoice_date", pa.timestamp("us")),
        ("price", pa.decimal128(18, 4)),
        ("customer_id", pa.int32()),
        ("country", pa.string()),
        ("is_cancellation", pa.bool_()),
    ]
)
DDL = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE TABLE IF NOT EXISTS {TABLE} (
    invoice text,
    stock_code text,
    description text,
    quantity integer,
    invoice_date timestamp,
    price numeric(18, 4),
    customer_id integer,
    country text,
    is_cancellation boolean
)
"""
QUANTUM = Decimal("0.0001")


def write_parquet(rows, path):
    columns = list(zip(*rows)) if rows else [()] * len(COLUMNS)
    columns[5] = tuple(price.quantize(QUANTUM) for price in columns[5])
    table = pa.Table.from_arrays(
        [pa.array(column, type=field.type) for column, field in zip(columns, PARQUET_SCHEMA)],
        schema=PARQUET_SCHEMA,
    )
    pq.write_table(table, path)


def replace_table(cursor, path):
    parquet = pq.ParquetFile(path)
    cursor.execute(DDL)
    cursor.execute(f"TRUNCATE {TABLE}")
    with cursor.copy(f"COPY {TABLE} ({', '.join(COLUMNS)}) FROM STDIN") as copy:
        for batch in parquet.iter_batches(batch_size=50000):
            for row in zip(*(batch.column(name).to_pylist() for name in COLUMNS)):
                copy.write_row(row)
    return parquet.metadata.num_rows


def check_table(cursor, expected):
    cursor.execute(f"SELECT count(*) FROM {TABLE}")
    count = cursor.fetchone()[0]
    if count != expected:
        raise ValueError(f"{TABLE} has {count} rows but the parquet has {expected}")
    for column in ("invoice", "stock_code", "quantity", "invoice_date", "price"):
        cursor.execute(f"SELECT count(*) FROM {TABLE} WHERE {column} IS NULL")
        nulls = cursor.fetchone()[0]
        if nulls:
            raise ValueError(f"{TABLE}.{column} has {nulls} NULL values")
    cursor.execute(
        f"SELECT count(*) FROM (SELECT 1 FROM {TABLE} GROUP BY {', '.join(COLUMNS)} "
        "HAVING count(*) > 1) AS repeated"
    )
    repeated = cursor.fetchone()[0]
    if repeated:
        raise ValueError(f"{TABLE} has {repeated} rows that repeat exactly")
    return {"rows": count, "null_free": True, "duplicate_free": True}
