import os
import shutil
import tempfile

import boto3

from .clean import clean
from .extract import read_workbook
from .load import load, write_parquet


class StepError(Exception):
    def __init__(self, step, cause):
        super().__init__(f"step={step} failed: {type(cause).__name__}: {' '.join(str(cause).split())}")
        self.step = step


def _split(uri):
    bucket, _, key = uri[len("s3://"):].partition("/")
    return bucket, key


def _download(uri, path):
    if uri.startswith("s3://"):
        bucket, key = _split(uri)
        boto3.client("s3").download_file(bucket, key, path)
        return path
    return uri


def _upload(path, uri):
    if uri.startswith("s3://"):
        bucket, key = _split(uri)
        boto3.client("s3").upload_file(path, bucket, key)
    else:
        shutil.copyfile(path, uri)
    return os.path.getsize(path)


def _step(name, function, *args):
    try:
        return function(*args)
    except Exception as error:
        raise StepError(name, error) from error


def run(input_uri, output_uri, conninfo, schema):
    with tempfile.TemporaryDirectory() as tmp:
        workbook = _step("extract", _download, input_uri, os.path.join(tmp, "input.xlsx"))
        first, second = _step("extract", read_workbook, workbook)
        kept, counts = _step("clean", clean, first, second)
        parquet = os.path.join(tmp, "out.parquet")
        _step("write", write_parquet, kept, parquet)
        size = _step("write", _upload, parquet, output_uri)
        loaded = _step("load", load, conninfo, schema, parquet)
    return {"counts": counts, "parquet": output_uri, "parquet_bytes": size, "loaded_rows": loaded}
