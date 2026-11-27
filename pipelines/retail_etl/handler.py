import os
import tempfile

import boto3
import psycopg

from .pipeline import run

BUCKET = "chaos-lab-903859731897"
INPUT_KEY = "online-retail-ii/online_retail_II.xlsx"
OUTPUT_KEY = "online-retail-ii/trials/issue-19/online_retail_ii.parquet"


def _connect():
    host = os.environ["DB_HOST"]
    port = int(os.environ.get("DB_PORT", "5432"))
    user = os.environ["DB_USER"]
    token = boto3.client("rds").generate_db_auth_token(
        DBHostname=host, Port=port, DBUsername=user
    )
    return psycopg.connect(
        host=host,
        port=port,
        user=user,
        password=token,
        dbname=os.environ.get("DB_NAME", "chaos_lab"),
        sslmode="require",
    )


def handler(event, context):
    s3 = boto3.client("s3")
    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        workbook = os.path.join(tmp, "workbook.xlsx")

        def fetch():
            s3.download_file(BUCKET, INPUT_KEY, workbook)
            return workbook

        def publish(path):
            s3.upload_file(path, BUCKET, OUTPUT_KEY)

        return run(_connect, fetch, publish, os.path.join(tmp, "out.parquet"))
