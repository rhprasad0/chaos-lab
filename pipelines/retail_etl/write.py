import pyarrow as pa
import pyarrow.parquet as pq

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

SCHEMA = pa.schema(
    [
        ("invoice", pa.string()),
        ("stock_code", pa.string()),
        ("description", pa.string()),
        ("quantity", pa.int32()),
        ("invoice_date", pa.timestamp("us")),
        ("price", pa.decimal128(12, 3)),
        ("customer_id", pa.int32()),
        ("country", pa.string()),
        ("is_cancellation", pa.bool_()),
    ]
)


def write_parquet(rows, path):
    columns = list(zip(*rows)) if rows else [()] * len(COLUMNS)
    table = pa.Table.from_arrays(
        [pa.array(values, type=field.type) for values, field in zip(columns, SCHEMA)], schema=SCHEMA
    )
    pq.write_table(table, path)
    return len(rows)
