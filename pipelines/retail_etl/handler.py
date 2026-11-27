import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import boto3

from retail_etl import etl, load

logger = logging.getLogger("retail_etl")
logger.setLevel(logging.INFO)


@contextmanager
def step(name):
    try:
        yield
    except Exception as error:
        logger.error("step=%s failed: %s: %s", name, type(error).__name__, error)
        raise


def run(workbook, parquet, dsn, download=None, upload=None):
    summary = {}
    with step("extract"):
        if download:
            download(workbook)
        sheets = etl.extract(workbook)
        logger.info("step=extract rows=%s", {name: len(rows) for name, rows in sheets.items()})
    with step("clean"):
        rows, counts = etl.clean(sheets)
        summary.update(counts)
        logger.info("step=clean %s", counts)
    with step("write"):
        etl.write_parquet(rows, parquet)
        if upload:
            upload(parquet)
        logger.info("step=write rows=%s", len(rows))
    with step("load"):
        checks = load.load(parquet, dsn)
    summary["checks"] = checks
    logger.info("step=load checks=%s", checks)
    return summary


def handler(event, context):
    bucket = os.environ["S3_BUCKET"]
    source_key = os.environ["SOURCE_KEY"]
    clean_key = os.environ["CLEAN_KEY"]
    s3 = boto3.client("s3")
    with tempfile.TemporaryDirectory() as tmp:
        return run(
            str(Path(tmp) / "workbook.xlsx"),
            str(Path(tmp) / "clean.parquet"),
            os.environ.get("DATABASE_URL", ""),
            download=lambda path: s3.download_file(bucket, source_key, path),
            upload=lambda path: s3.upload_file(path, bucket, clean_key),
        )
