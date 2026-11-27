import pyarrow.parquet as pq

from .errors import PipelineError

SCHEMA = "trial_issue_19"
TABLE = f"{SCHEMA}.transactions"
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
NOT_NULL = ("invoice", "stock_code", "quantity", "invoice_date", "price")

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
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


def _check(cur, expected):
    cur.execute(f"SELECT count(*) FROM {TABLE}")
    loaded = cur.fetchone()[0]
    if loaded != expected:
        raise PipelineError("check", f"{TABLE} has {loaded} rows, the parquet has {expected}")
    for column in NOT_NULL:
        cur.execute(f"SELECT count(*) FROM {TABLE} WHERE {column} IS NULL")
        nulls = cur.fetchone()[0]
        if nulls:
            raise PipelineError("check", f"{TABLE}.{column} has {nulls} NULL values")
    cols = ", ".join(COLUMNS)
    cur.execute(
        f"SELECT count(*) FROM (SELECT 1 FROM {TABLE} GROUP BY {cols} HAVING count(*) > 1) d"
    )
    duplicates = cur.fetchone()[0]
    if duplicates:
        raise PipelineError("check", f"{TABLE} has {duplicates} exact duplicate row groups")
    return {"rows": loaded, "null_checks": "passed", "duplicate_rows": 0}


def load(connect, parquet_path):
    parquet = pq.ParquetFile(parquet_path)
    expected = parquet.metadata.num_rows
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (SCHEMA,))
            if cur.fetchone() is None:
                cur.execute(f"CREATE SCHEMA {SCHEMA}")
            cur.execute(DDL)
            cur.execute(f"DELETE FROM {TABLE}")
            with cur.copy(f"COPY {TABLE} ({', '.join(COLUMNS)}) FROM STDIN") as copy:
                for batch in parquet.iter_batches(batch_size=50000):
                    for row in zip(*(batch.column(name).to_pylist() for name in COLUMNS)):
                        copy.write_row(row)
            result = _check(cur, expected)
    return result
