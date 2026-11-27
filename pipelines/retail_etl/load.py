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
NOT_NULL = ("invoice", "stock_code", "quantity", "invoice_date", "price")


def load_parquet(connection, schema, parquet_path):
    table = f"{schema}.transactions"
    expected = pq.ParquetFile(parquet_path).metadata.num_rows
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
            cursor.execute(
                f"""CREATE TABLE IF NOT EXISTS {table} (
                    invoice text,
                    stock_code text,
                    description text,
                    quantity integer,
                    invoice_date timestamp,
                    price numeric(18, 4),
                    customer_id integer,
                    country text,
                    is_cancellation boolean
                )"""
            )
            cursor.execute(f"TRUNCATE {table}")
            with cursor.copy(f"COPY {table} ({', '.join(COLUMNS)}) FROM STDIN") as copy:
                for batch in pq.ParquetFile(parquet_path).iter_batches(batch_size=50000):
                    for row in zip(*(batch.column(name).to_pylist() for name in COLUMNS)):
                        copy.write_row(row)
            check(cursor, table, expected)
    return expected


def check(cursor, table, expected):
    cursor.execute(f"SELECT count(*) FROM {table}")
    count = cursor.fetchone()[0]
    if count != expected:
        raise ValueError(f"{table} has {count} rows, the parquet has {expected}")
    for column in NOT_NULL:
        cursor.execute(f"SELECT count(*) FROM {table} WHERE {column} IS NULL")
        nulls = cursor.fetchone()[0]
        if nulls:
            raise ValueError(f"{table}.{column} has {nulls} NULL values")
    cursor.execute(
        f"SELECT count(*) FROM (SELECT 1 FROM {table} GROUP BY {', '.join(COLUMNS)} HAVING count(*) > 1) d"
    )
    duplicates = cursor.fetchone()[0]
    if duplicates:
        raise ValueError(f"{table} has {duplicates} groups of exact duplicate rows")
