import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb
import psycopg
from retail import clean, ingest
from retail.config import load_config

HERE = Path(__file__).parent
ANALYSIS = ("sale", "return", "unmatched_return", "guest_return")
COLUMNS = ("invoice", "stock_code", "description", "quantity", "invoice_date", "price", "customer_id", "country", "is_cancellation")
REQUIRED = ("invoice", "stock_code", "quantity", "invoice_date", "price")
TABLE = """
create schema if not exists retail;
create table if not exists retail.transactions (
    invoice text,
    stock_code text,
    description text,
    quantity integer,
    invoice_date timestamp,
    price numeric(12, 3),
    customer_id integer,
    country text,
    is_cancellation boolean
)
"""

log = logging.getLogger("retail_etl")
log.setLevel(logging.INFO)


class CheckError(RuntimeError):
    pass


def step(name, function, *args):
    try:
        return function(*args)
    except Exception as error:
        log.error("step=%s failed: %s: %s", name, type(error).__name__, error)
        raise


def transform(workbook, parquet):
    with tempfile.TemporaryDirectory() as work:
        work = Path(work)
        (work / "data" / "raw").mkdir(parents=True)
        shutil.copy(workbook, work / "data" / "raw" / "online_retail_II.xlsx")
        shutil.copy(HERE / "config.toml", work / "config.toml")
        cfg = load_config(work / "config.toml")
        ingest.run(cfg)
        clean.run(cfg)
        con = duckdb.connect(str(cfg.paths.database), read_only=True)
        con.execute(f"""
            copy (
                select invoice, stock_code, description, quantity, line_time as invoice_date, price,
                       customer_id, country, is_cancel as is_cancellation
                from lines where outcome in {ANALYSIS} order by raw_id
            ) to '{parquet}' (format parquet, compression zstd)
        """)
        return con.execute(f"select count(*) from read_parquet('{parquet}')").fetchone()[0]


def load(connection, parquet):
    rows = duckdb.sql(f"select {', '.join(COLUMNS)} from read_parquet('{parquet}')").fetchall()
    with connection.transaction(), connection.cursor() as cur:
        cur.execute(TABLE)
        cur.execute("truncate retail.transactions")
        with cur.copy(f"copy retail.transactions ({', '.join(COLUMNS)}) from stdin") as copy:
            for row in rows:
                copy.write_row(row)
        check(cur, len(rows))
    return len(rows)


def check(cur, expected):
    nulls = " + ".join(f"count(*) filter (where {c} is null)" for c in REQUIRED)
    cur.execute(f"select count(*), {nulls} from retail.transactions")
    loaded, null_count = cur.fetchone()
    if loaded != expected:
        raise CheckError(f"retail.transactions has {loaded} rows, the parquet has {expected}")
    if null_count:
        raise CheckError(f"{null_count} NULLs in required columns {REQUIRED}")
    cur.execute(f"select count(*) - count(distinct ({', '.join(COLUMNS)})) from retail.transactions")
    duplicates = cur.fetchone()[0]
    if duplicates:
        raise CheckError(f"{duplicates} exact duplicate rows in retail.transactions")


def database():
    import boto3

    host, port, user = os.environ["DB_HOST"], int(os.environ["DB_PORT"]), os.environ["DB_USER"]
    token = boto3.client("rds").generate_db_auth_token(DBHostname=host, Port=port, DBUsername=user)
    return psycopg.connect(host=host, port=port, dbname=os.environ["DB_NAME"], user=user, password=token,
                           sslmode="verify-full", sslrootcert=str(HERE / "rds-ca-bundle.pem"))


def handler(event, context):
    import boto3

    s3 = boto3.client("s3")
    bucket = os.environ["BUCKET"]
    with tempfile.TemporaryDirectory() as work:
        workbook, parquet = Path(work) / "input.xlsx", Path(work) / "clean.parquet"
        step("extract", s3.download_file, bucket, os.environ["INPUT_KEY"], str(workbook))
        cleaned = step("transform", transform, workbook, parquet)
        step("write", s3.upload_file, str(parquet), bucket, os.environ["OUTPUT_KEY"])
        connection = step("connect", database)
        with connection:
            loaded = step("load", load, connection, parquet)
    print(f"cleaned={cleaned} loaded={loaded}")
    return {"cleaned": cleaned, "loaded": loaded}


def main():
    logging.basicConfig(format="%(message)s")
    workbook, parquet = sys.argv[1:3]
    cleaned = step("transform", transform, workbook, parquet)
    with psycopg.connect("") as connection:
        loaded = step("load", load, connection, parquet)
    print(f"cleaned={cleaned} loaded={loaded}")


if __name__ == "__main__":
    main()
