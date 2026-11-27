import pyarrow as pa
import pyarrow.parquet as pq

PRICE_TYPE = pa.decimal128(14, 4)
SCHEMA = pa.schema(
    [
        ("invoice", pa.string()),
        ("stock_code", pa.string()),
        ("description", pa.string()),
        ("quantity", pa.int32()),
        ("invoice_date", pa.timestamp("us")),
        ("price", PRICE_TYPE),
        ("customer_id", pa.int64()),
        ("country", pa.string()),
        ("is_cancellation", pa.bool_()),
    ]
)


def write_parquet(rows, path):
    columns = list(zip(*rows)) if rows else [()] * len(SCHEMA)
    table = pa.table(
        {field.name: pa.array(col, type=field.type) for field, col in zip(SCHEMA, columns)},
        schema=SCHEMA,
    )
    pq.write_table(table, path)
