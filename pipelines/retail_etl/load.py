import pyarrow.parquet as pq
import psycopg

from retail_etl.etl import COLUMNS, REQUIRED, SCHEMA

TABLE = "retail.transactions"
ALL_COLUMNS = ", ".join(field.name for field in SCHEMA)

DDL = f"""
CREATE SCHEMA IF NOT EXISTS retail;
CREATE TABLE IF NOT EXISTS {TABLE} (
    invoice text,
    stock_code text,
    description text,
    quantity integer,
    invoice_date timestamp,
    price numeric(12, 4),
    customer_id integer,
    country text,
    is_cancellation boolean NOT NULL
)
"""


class CheckError(Exception):
    pass


def load(parquet_path, dsn):
    parquet = pq.ParquetFile(parquet_path)
    expected = parquet.metadata.num_rows
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute(f"TRUNCATE {TABLE}")
        with cur.copy(f"COPY {TABLE} ({ALL_COLUMNS}) FROM STDIN") as copy:
            for batch in parquet.iter_batches():
                for row in zip(*(column.to_pylist() for column in batch.columns)):
                    copy.write_row(row)
        checks = check(cur, expected)
    return checks


def check(cur, expected):
    cur.execute(f"SELECT count(*) FROM {TABLE}")
    loaded = cur.fetchone()[0]
    results = {"parquet_rows": expected, "table_rows": loaded}
    failures = []
    if loaded != expected:
        failures.append(f"table has {loaded} rows, parquet has {expected}")
    for column in REQUIRED:
        cur.execute(f"SELECT count(*) FROM {TABLE} WHERE {column} IS NULL")
        nulls = cur.fetchone()[0]
        results[f"null_{column}"] = nulls
        if nulls:
            failures.append(f"{nulls} rows have NULL {column}")
    cur.execute(
        f"SELECT coalesce(sum(n - 1), 0) FROM "
        f"(SELECT count(*) AS n FROM {TABLE} GROUP BY {ALL_COLUMNS} HAVING count(*) > 1) d"
    )
    duplicates = cur.fetchone()[0]
    results["duplicate_rows"] = int(duplicates)
    if duplicates:
        failures.append(f"{duplicates} exact duplicate rows")
    if failures:
        raise CheckError("; ".join(failures))
    return results
