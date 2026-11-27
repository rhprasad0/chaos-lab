import logging
import os
from contextlib import contextmanager

import boto3

from .clean import clean
from .extract import extract
from .load import CheckError, load_parquet
from .write import write_parquet

LOGGER = logging.getLogger("retail_etl")


class StepError(Exception):
    pass


@contextmanager
def step(name):
    try:
        yield
    except Exception as error:
        failed = "check" if isinstance(error, CheckError) else name
        LOGGER.error("ETL step %s failed: %s: %s", failed, type(error).__name__, error)
        raise StepError(f"step {failed} failed: {type(error).__name__}: {error}") from error


def split_uri(uri):
    bucket, _, key = uri.removeprefix("s3://").partition("/")
    return bucket, key


def run(source, target, schema, connect, workdir, s3=None):
    local_source = source
    local_target = target
    if target.startswith("s3://"):
        local_target = os.path.join(workdir, "target.parquet")
    with step("extract"):
        if source.startswith("s3://"):
            local_source = os.path.join(workdir, "source.xlsx")
            s3 = s3 or boto3.client("s3")
            s3.download_file(*split_uri(source), local_source)
        sheets = extract(local_source)
    with step("clean"):
        kept, outcomes = clean(sheets)
    with step("write"):
        write_parquet(kept, local_target)
        if target.startswith("s3://"):
            s3 = s3 or boto3.client("s3")
            s3.upload_file(local_target, *split_uri(target))
    with step("load"):
        with connect() as connection:
            rows = load_parquet(connection, schema, local_target)
    LOGGER.info("ETL loaded %s rows; outcomes %s", rows, outcomes)
    return {"rows": rows, "outcomes": outcomes}
