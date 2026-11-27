import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
from psycopg import sql

SCHEMA = pa.schema(
    [
        ("invoice", pa.string()),
        ("stock_code", pa.string()),
        ("description", pa.string()),
        ("quantity", pa.int32()),
        ("invoice_date", pa.timestamp("us")),
        ("price", pa.decimal128(14, 4)),
        ("customer_id", pa.int32()),
        ("country", pa.string()),
        ("is_cancellation", pa.bool_()),
    ]
)
COLUMNS = SCHEMA.names
NOT_NULL = ("invoice", "stock_code", "quantity", "invoice_date", "price")

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS {table} (
    invoice text,
    stock_code text,
    description text,
    quantity integer,
    invoice_date timestamp,
    price numeric(14, 4),
    customer_id integer,
    country text,
    is_cancellation boolean
)
"""


class CheckError(Exception):
    pass


def write_parquet(rows, path):
    columns = list(zip(*rows)) if rows else [()] * len(COLUMNS)
    table = pa.table(dict(zip(COLUMNS, columns)), schema=SCHEMA)
    pq.write_table(table, path)


def load(conninfo, schema, parquet_path):
    parquet = pq.ParquetFile(parquet_path)
    expected = parquet.metadata.num_rows
    table = sql.Identifier(schema, "transactions")
    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            cur.execute(sql.SQL(CREATE_TABLE).format(table=table))
            cur.execute(sql.SQL("TRUNCATE {}").format(table))
            with cur.copy(sql.SQL("COPY {} ({}) FROM STDIN").format(table, sql.SQL(", ").join(map(sql.Identifier, COLUMNS)))) as copy:
                for batch in parquet.iter_batches(batch_size=50_000):
                    for row in zip(*(batch.column(name).to_pylist() for name in COLUMNS)):
                        copy.write_row(row)
            _check(cur, table, expected)
    return expected


def _check(cur, table, expected):
    cur.execute(sql.SQL("SELECT count(*) FROM {}").format(table))
    loaded = cur.fetchone()[0]
    if loaded != expected:
        raise CheckError(f"row count check failed: table has {loaded} rows, parquet has {expected}")
    for column in NOT_NULL:
        cur.execute(sql.SQL("SELECT count(*) FROM {} WHERE {} IS NULL").format(table, sql.Identifier(column)))
        nulls = cur.fetchone()[0]
        if nulls:
            raise CheckError(f"NULL check failed: {nulls} rows have NULL {column}")
    cur.execute(
        sql.SQL("SELECT count(*) FROM (SELECT 1 FROM {} GROUP BY {} HAVING count(*) > 1) AS d").format(
            table, sql.SQL(", ").join(map(sql.Identifier, COLUMNS))
        )
    )
    duplicates = cur.fetchone()[0]
    if duplicates:
        raise CheckError(f"duplicate check failed: {duplicates} row groups repeat exactly")
