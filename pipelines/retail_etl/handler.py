import logging
import os
import tempfile
from pathlib import Path

import boto3
import psycopg

from retail_etl.load import load_parquet
from retail_etl.transform import clean, read_workbook, write_parquet

ISSUE = 15
SCHEMA = f"trial_issue_{ISSUE}"
BUCKET = "chaos-lab-903859731897"
INPUT_KEY = "online-retail-ii/online_retail_II.xlsx"
OUTPUT_KEY = f"online-retail-ii/trials/issue-{ISSUE}/online_retail_ii.parquet"

logger = logging.getLogger("retail_etl")
logger.setLevel(logging.INFO)


def step(name, action, *args):
    try:
        return action(*args)
    except Exception as error:
        logger.error("etl step=%s failed: %s: %s", name, type(error).__name__, error)
        raise


def run(workbook_path, parquet_path, connect, upload=None):
    first, second = step("extract", read_workbook, workbook_path)
    kept, outcomes = step("clean", clean, first, second)
    step("write", write_parquet, kept, parquet_path)
    if upload:
        step("upload", upload, parquet_path)

    def load():
        with connect() as connection:
            return load_parquet(connection, SCHEMA, parquet_path)

    loaded = step("load", load)
    logger.info("etl done outcomes=%s loaded=%s", dict(outcomes), loaded)
    return outcomes, loaded


def connect_with_iam():
    host = os.environ["DB_HOST"]
    port = int(os.environ.get("DB_PORT", "5432"))
    user = os.environ["DB_USER"]
    token = boto3.client("rds").generate_db_auth_token(DBHostname=host, Port=port, DBUsername=user)
    return psycopg.connect(
        host=host,
        port=port,
        dbname=os.environ["DB_NAME"],
        user=user,
        password=token,
        sslmode="require",
    )


def handler(event, context):
    s3 = boto3.client("s3")
    with tempfile.TemporaryDirectory() as directory:
        workbook_path = Path(directory) / "online_retail_II.xlsx"
        parquet_path = Path(directory) / "online_retail_ii.parquet"
        step("download", s3.download_file, BUCKET, INPUT_KEY, str(workbook_path))
        outcomes, loaded = run(
            workbook_path,
            parquet_path,
            connect_with_iam,
            lambda path: s3.upload_file(str(path), BUCKET, OUTPUT_KEY),
        )
    return {"outcomes": dict(outcomes), "loaded": loaded}
