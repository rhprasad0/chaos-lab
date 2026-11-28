import hashlib
import logging
import os
import re
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import psycopg

import contract

HERE = Path(__file__).parent
ANALYSIS = ("sale", "return", "unmatched_return", "guest_return")
COLUMNS = ("invoice", "stock_code", "description", "quantity", "invoice_date", "price", "customer_id", "country", "is_cancellation")
TEXT_COLUMNS = ("Invoice", "StockCode", "Description", "Country")
TABLE = """
create schema if not exists {schema};
create table if not exists {schema}.transactions (
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
LEDGER = """
create schema if not exists {schema};
create table if not exists {schema}.etl_runs (
    run_id text primary key,
    started_at timestamptz not null,
    ended_at timestamptz not null,
    input_version_id text,
    input_sha256 text,
    code_version text not null,
    rows_extracted integer,
    rows_cleaned integer,
    rows_loaded integer,
    status text not null,
    failed_step text,
    error text
)
"""

log = logging.getLogger("retail_etl")
log.setLevel(logging.INFO)


def step(name, function, *args):
    try:
        return function(*args)
    except Exception as error:
        log.error("step=%s failed: %s: %s", name, type(error).__name__, error)
        error.failed_step = name
        raise


def schema():
    name = os.environ.get("DB_SCHEMA", "retail")
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise ValueError(f"DB_SCHEMA {name!r} is not a plain lowercase identifier")
    return name


def code_version():
    path = HERE / "GIT_SHA"
    return path.read_text().strip() if path.is_file() else "unknown"


def as_text(value):
    if value is None or value != value:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def as_numbers(column, integral):
    numbers = pd.to_numeric(column, errors="coerce")
    if numbers.isna().sum() != column.isna().sum():
        return column
    if integral and (numbers.dropna() % 1 == 0).all():
        return numbers.astype("Int64")
    return numbers if integral else numbers.astype("float64")


def as_timestamps(column):
    stamps = pd.to_datetime(column, errors="coerce")
    return column if stamps.isna().sum() != column.isna().sum() else stamps


def parse_workbook(path):
    from python_calamine import CalamineWorkbook

    book = CalamineWorkbook.from_path(str(path))
    frames = []
    for name in book.sheet_names:
        rows = book.get_sheet_by_name(name).to_python()
        if not rows:
            continue
        frame = pd.DataFrame(rows[1:], columns=[str(cell).strip() for cell in rows[0]])
        frame = frame.mask(frame == "").dropna(how="all")
        frame.insert(0, "sheet", name)
        frames.append(frame)
    frame = pd.concat(frames, ignore_index=True)
    for column in TEXT_COLUMNS:
        if column in frame:
            frame[column] = frame[column].map(as_text)
    for column, integral in (("Quantity", True), ("Customer ID", True), ("Price", False)):
        if column in frame:
            frame[column] = as_numbers(frame[column], integral)
    if "InvoiceDate" in frame:
        frame["InvoiceDate"] = as_timestamps(frame["InvoiceDate"])
    return frame


def extract(fetch, workbook, state):
    state["input_version_id"], state["input_sha256"] = fetch(workbook)
    return parse_workbook(workbook)


def transform(workbook, parquet):
    from retail import clean, ingest
    from retail.config import load_config

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
    with connection.cursor() as cur:
        cur.execute(TABLE.format(schema=schema()))
        cur.execute(f"truncate {schema()}.transactions")
        with cur.copy(f"copy {schema()}.transactions ({', '.join(COLUMNS)}) from stdin") as copy:
            for row in rows:
                copy.write_row(row)
    return len(rows)


def check_output(connection, parquet):
    expected = duckdb.sql(f"select count(*) from read_parquet('{parquet}')").fetchone()[0]
    with connection.cursor() as cur:
        contract.check_output(cur, schema(), contract.load("output.yaml"), expected)


def record(connect, state):
    with connect() as connection, connection.transaction(), connection.cursor() as cur:
        cur.execute(LEDGER.format(schema=schema()))
        cur.execute(
            f"""insert into {schema()}.etl_runs
                (run_id, started_at, ended_at, input_version_id, input_sha256, code_version,
                 rows_extracted, rows_cleaned, rows_loaded, status, failed_step, error)
                values (%(run_id)s, %(started_at)s, %(ended_at)s, %(input_version_id)s, %(input_sha256)s,
                        %(code_version)s, %(rows_extracted)s, %(rows_cleaned)s, %(rows_loaded)s,
                        %(status)s, %(failed_step)s, %(error)s)""",
            state,
        )


def process(fetch, workbook, parquet, connect, write=None, publish=None, run_id=None):
    state = dict.fromkeys(
        ("input_version_id", "input_sha256", "rows_extracted", "rows_cleaned", "rows_loaded", "failed_step", "error")
    )
    state.update(run_id=run_id or str(uuid.uuid4()), started_at=datetime.now(timezone.utc), code_version=code_version())
    try:
        frame = step("extract", extract, fetch, workbook, state)
        state["rows_extracted"] = len(frame)
        step("input_contract", contract.check_input, frame, contract.load("input.yaml"))
        del frame
        state["rows_cleaned"] = step("transform", transform, workbook, parquet)
        if write:
            step("write", write, parquet)
        connection = step("connect", connect)
        with connection:
            with connection.transaction():
                loaded = step("load", load, connection, parquet)
                step("output_contract", check_output, connection, parquet)
        state["rows_loaded"] = loaded
        if publish:
            step("publish", publish)
        state["status"] = "succeeded"
    except Exception as error:
        state.update(status="failed", failed_step=getattr(error, "failed_step", "unknown"), error=f"{type(error).__name__}: {error}"[:500])
        state["ended_at"] = datetime.now(timezone.utc)
        try:
            step("ledger", record, connect, state)
        except Exception:
            pass
        raise
    state["ended_at"] = datetime.now(timezone.utc)
    step("ledger", record, connect, state)
    return state


def database():
    import boto3

    host, port, user = os.environ["DB_HOST"], int(os.environ["DB_PORT"]), os.environ["DB_USER"]
    token = boto3.client("rds").generate_db_auth_token(DBHostname=host, Port=port, DBUsername=user)
    return psycopg.connect(host=host, port=port, dbname=os.environ["DB_NAME"], user=user, password=token,
                           sslmode="verify-full", sslrootcert=str(HERE / "rds-ca-bundle.pem"))


def hashed_copy(source, workbook):
    digest = hashlib.sha256()
    with open(workbook, "wb") as target:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
            target.write(block)
    return digest.hexdigest()


def handler(event, context):
    import boto3

    s3 = boto3.client("s3")
    bucket, input_key, output_key = os.environ["BUCKET"], os.environ["INPUT_KEY"], os.environ["OUTPUT_KEY"]
    staging_key = output_key + ".staging"

    def fetch(workbook):
        response = s3.get_object(Bucket=bucket, Key=input_key)
        return response.get("VersionId"), hashed_copy(response["Body"], workbook)

    def write(parquet):
        s3.upload_file(str(parquet), bucket, staging_key)

    def publish():
        s3.copy_object(Bucket=bucket, Key=output_key, CopySource={"Bucket": bucket, "Key": staging_key})

    with tempfile.TemporaryDirectory() as work:
        state = process(fetch, Path(work) / "input.xlsx", Path(work) / "clean.parquet", database, write, publish,
                        getattr(context, "aws_request_id", None))
    print(f"cleaned={state['rows_cleaned']} loaded={state['rows_loaded']}")
    return {"cleaned": state["rows_cleaned"], "loaded": state["rows_loaded"]}


def main():
    logging.basicConfig(format="%(message)s")
    workbook, parquet = sys.argv[1:3]

    def fetch(copy):
        with open(workbook, "rb") as source:
            return None, hashed_copy(source, copy)

    with tempfile.TemporaryDirectory() as work:
        state = process(fetch, Path(work) / "input.xlsx", Path(parquet), lambda: psycopg.connect(""))
    print(f"cleaned={state['rows_cleaned']} loaded={state['rows_loaded']}")


if __name__ == "__main__":
    main()
