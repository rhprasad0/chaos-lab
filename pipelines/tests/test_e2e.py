import hashlib
import os
import re
import subprocess
import types
import urllib.request
import zipfile
from pathlib import Path

import boto3
import duckdb
import psycopg
import pytest
from moto import mock_aws

import contract
import etl

UCI_URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
UCI_SHA256 = "572e36277c2390fbfde10664750731e0a86f55e33470d91919085f0408e67bfb"
ETL = Path(__file__).parents[1] / "retail_etl"
BUCKET = "lab"
INPUT_KEY = "online-retail-ii/online_retail_II.xlsx"
OUTPUT_KEY = "online-retail-ii/clean/online_retail_ii.parquet"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="session")
def workbook(tmp_path_factory):
    cache = Path(os.environ.get("CHAOS_LAB_CACHE", Path.home() / ".cache" / "chaos-lab"))
    archive = cache / "online_retail_ii.zip"
    if not archive.is_file() or sha256(archive) != UCI_SHA256:
        cache.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(UCI_URL, archive)
    assert sha256(archive) == UCI_SHA256
    path = tmp_path_factory.mktemp("workbook") / "online_retail_II.xlsx"
    with zipfile.ZipFile(archive) as source:
        path.write_bytes(source.read("online_retail_II.xlsx"))
    return path


@pytest.fixture(scope="session")
def renamed_price(workbook, tmp_path_factory):
    path = tmp_path_factory.mktemp("broken") / "online_retail_II.xlsx"
    with zipfile.ZipFile(workbook) as source, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item)
            if item.filename == "xl/sharedStrings.xml":
                assert data.count(b"<t>Price</t>") == 1
                data = data.replace(b"<t>Price</t>", b"<t>UnitPrice</t>")
            target.writestr(item, data)
    return path


@pytest.fixture(scope="session")
def reference(tmp_path_factory):
    root = tmp_path_factory.mktemp("reference") / "src"
    subprocess.run(["bash", "-c", f'source "{ETL}/reference.sh" && fetch_reference "{root}"'], check=True)
    return root


@pytest.fixture
def lab(reference, db_schema, monkeypatch, tmp_path):
    config = (reference / "config.toml").read_text()
    (tmp_path / "config.toml").write_text(re.sub(r"(?m)^sha256 = .*$", 'sha256 = ""', config))
    monkeypatch.syspath_prepend(str(reference))
    monkeypatch.setattr(etl, "HERE", tmp_path)
    monkeypatch.setattr(etl, "database", lambda: psycopg.connect(""))
    env = {"BUCKET": BUCKET, "INPUT_KEY": INPUT_KEY, "OUTPUT_KEY": OUTPUT_KEY, "AWS_DEFAULT_REGION": "us-east-1",
           "AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test"}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with mock_aws():
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket=BUCKET)
        s3.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
        yield s3


def upload(s3, path):
    return s3.put_object(Bucket=BUCKET, Key=INPUT_KEY, Body=Path(path).read_bytes())["VersionId"]


def seed_previous_run(s3):
    s3.put_object(Bucket=BUCKET, Key=OUTPUT_KEY, Body=b"previous")
    with psycopg.connect("") as connection:
        connection.execute(etl.TABLE.format(schema=etl.schema()))
        connection.execute(f"insert into {etl.schema()}.transactions (invoice) values ('previous')")


def invoke(request_id):
    return etl.handler({}, types.SimpleNamespace(aws_request_id=request_id))


def ledger():
    with psycopg.connect("") as connection:
        return connection.execute(
            f"select status, failed_step, error, input_version_id, input_sha256, rows_extracted, rows_cleaned, rows_loaded "
            f"from {etl.schema()}.etl_runs"
        ).fetchall()


def table():
    with psycopg.connect("") as connection:
        return connection.execute(f"select count(*), min(invoice) from {etl.schema()}.transactions").fetchone()


def published(s3, tmp_path):
    path = tmp_path / "published.parquet"
    s3.download_file(BUCKET, OUTPUT_KEY, str(path))
    return path


def test_a_clean_run_publishes_loads_and_records_the_input(lab, workbook, tmp_path):
    version = upload(lab, workbook)
    assert invoke("clean") == {"cleaned": 1018816, "loaded": 1018816}
    rows, total = duckdb.sql(f"select count(*), sum(quantity * price) from read_parquet('{published(lab, tmp_path)}')").fetchone()
    assert (rows, round(float(total), 2)) == (1018816, 18927435.65)
    assert table()[0] == 1018816
    assert ledger() == [("succeeded", None, None, version, sha256(workbook), 1067371, 1018816, 1018816)]


def test_a_renamed_column_fails_the_input_contract_and_keeps_the_previous_outputs(lab, renamed_price):
    seed_previous_run(lab)
    version = upload(lab, renamed_price)
    with pytest.raises(contract.ContractError, match="rule=column_present column=Price"):
        invoke("renamed")
    assert lab.get_object(Bucket=BUCKET, Key=OUTPUT_KEY)["Body"].read() == b"previous"
    assert table() == (1, "previous")
    [(status, step, error, input_version, *_)] = ledger()
    assert (status, step, input_version) == ("failed", "input_contract", version)
    assert "column=Price" in error


def test_a_failed_output_contract_keeps_the_previous_outputs(lab, workbook, monkeypatch):
    load = contract.load

    def tightened(name):
        spec = load(name)
        if name == "output.yaml":
            spec["sum"]["expected"] *= 2
        return spec

    monkeypatch.setattr(contract, "load", tightened)
    seed_previous_run(lab)
    upload(lab, workbook)
    with pytest.raises(contract.ContractError, match="rule=sum"):
        invoke("tightened")
    assert lab.get_object(Bucket=BUCKET, Key=OUTPUT_KEY)["Body"].read() == b"previous"
    assert table() == (1, "previous")
    [(status, step, *_rest, rows_loaded)] = ledger()
    assert (status, step, rows_loaded) == ("failed", "output_contract", None)
