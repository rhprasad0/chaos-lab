import pyarrow.parquet as pq
from psycopg import sql

from .write import COLUMNS

TABLE_COLUMNS = """
    invoice text,
    stock_code text,
    description text,
    quantity integer,
    invoice_date timestamp,
    price numeric(12, 3),
    customer_id integer,
    country text,
    is_cancellation boolean
"""
NOT_NULL = ("invoice", "stock_code", "quantity", "invoice_date", "price")


class CheckError(Exception):
    pass


def _count(cursor, query, *args):
    cursor.execute(query, args)
    return cursor.fetchone()[0]


def check(cursor, table, expected_rows):
    loaded = _count(cursor, sql.SQL("SELECT count(*) FROM {}").format(table))
    if loaded != expected_rows:
        raise CheckError(f"table has {loaded} rows but the parquet has {expected_rows}")
    for column in NOT_NULL:
        nulls = _count(
            cursor, sql.SQL("SELECT count(*) FROM {} WHERE {} IS NULL").format(table, sql.Identifier(column))
        )
        if nulls:
            raise CheckError(f"{nulls} rows have NULL {column}")
    columns = sql.SQL(", ").join(map(sql.Identifier, COLUMNS))
    duplicates = _count(
        cursor,
        sql.SQL("SELECT count(*) FROM (SELECT 1 FROM {} GROUP BY {} HAVING count(*) > 1) AS d").format(
            table, columns
        ),
    )
    if duplicates:
        raise CheckError(f"{duplicates} groups of exact duplicate rows remain")


def load_parquet(connection, schema, path):
    parquet = pq.ParquetFile(path)
    table = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier("transactions"))
    columns = sql.SQL(", ").join(map(sql.Identifier, COLUMNS))
    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        cursor.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(table, sql.SQL(TABLE_COLUMNS)))
        cursor.execute(sql.SQL("TRUNCATE {}").format(table))
        with cursor.copy(sql.SQL("COPY {} ({}) FROM STDIN").format(table, columns)) as copy:
            for batch in parquet.iter_batches(batch_size=50000):
                columns_data = [batch.column(name).to_pylist() for name in COLUMNS]
                for row in zip(*columns_data):
                    copy.write_row(row)
        check(cursor, table, parquet.metadata.num_rows)
    return parquet.metadata.num_rows
