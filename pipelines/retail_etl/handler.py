import logging
import os

import boto3
import psycopg

from .config import BUCKET, PARQUET_KEY, WORKBOOK_KEY
from .pipeline import StepError, run

logging.getLogger().setLevel(logging.INFO)


def _connect():
    host = os.environ["DB_HOST"]
    port = int(os.environ.get("DB_PORT", "5432"))
    user = os.environ["DB_USER"]
    token = boto3.client("rds").generate_db_auth_token(DBHostname=host, Port=port, DBUsername=user)
    return psycopg.connect(
        host=host,
        port=port,
        user=user,
        password=token,
        dbname=os.environ["DB_NAME"],
        sslmode="require",
    )


def handler(event, context):
    workbook_path = "/tmp/online_retail_II.xlsx"
    parquet_path = "/tmp/online_retail_ii.parquet"
    try:
        s3 = boto3.client("s3")
        s3.download_file(BUCKET, WORKBOOK_KEY, workbook_path)
    except Exception as error:
        reason = " ".join(f"{type(error).__name__}: {error}".split())
        logging.getLogger("retail_etl").error("ETL step extract failed: %s", reason)
        raise StepError("extract", reason) from error
    return run(
        workbook_path,
        parquet_path,
        _connect,
        lambda path: s3.upload_file(path, BUCKET, PARQUET_KEY),
    )
