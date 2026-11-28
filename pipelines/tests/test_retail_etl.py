import os
import sys
from pathlib import Path

import duckdb
import pytest

PACKAGE = Path(__file__).parent.parent / "retail_etl" / "build" / "package"
WORKBOOK = os.environ.get("CHAOS_LAB_WORKBOOK")
pytestmark = pytest.mark.skipif(
    not (WORKBOOK and os.environ.get("PGHOST") and PACKAGE.is_dir()),
    reason="needs CHAOS_LAB_WORKBOOK, a disposable PG* database and pipelines/retail_etl/package.sh",
)
if PACKAGE.is_dir():
    sys.path.insert(0, str(PACKAGE))


@pytest.fixture(scope="module")
def parquet(tmp_path_factory):
    import etl

    path = tmp_path_factory.mktemp("etl") / "clean.parquet"
    etl.transform(WORKBOOK, path)
    return path


@pytest.fixture
def connection():
    import psycopg

    with psycopg.connect("") as con:
        con.execute("drop schema if exists retail cascade")
        con.commit()
        yield con


def count(connection):
    return connection.execute("select count(*) from retail.transactions").fetchone()[0]


def test_the_parquet_holds_the_analysis_rows(parquet):
    assert duckdb.sql(f"select count(*) from read_parquet('{parquet}')").fetchone()[0] == 1018816


def test_a_rerun_replaces_the_table(parquet, connection):
    import etl

    assert etl.load(connection, parquet) == etl.load(connection, parquet) == count(connection) == 1018816


def test_a_failed_check_keeps_the_previous_rows(parquet, connection, tmp_path):
    import etl

    etl.load(connection, parquet)
    broken = tmp_path / "broken.parquet"
    duckdb.sql(f"copy (select * replace (null as price) from read_parquet('{parquet}') limit 10) to '{broken}' (format parquet)")
    with pytest.raises(etl.CheckError, match="NULLs"):
        etl.load(connection, broken)
    assert count(connection) == 1018816


def test_the_handler_reads_and_writes_the_lab_keys(parquet, connection, monkeypatch, capsys):
    import boto3
    import etl
    import psycopg
    from moto import mock_aws

    env = {"BUCKET": "lab", "INPUT_KEY": "in/online_retail_II.xlsx", "OUTPUT_KEY": "out/clean.parquet",
           "AWS_DEFAULT_REGION": "us-east-1", "AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test"}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(etl, "database", lambda: psycopg.connect(""))
    with mock_aws():
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket="lab")
        s3.upload_file(WORKBOOK, "lab", env["INPUT_KEY"])
        assert etl.handler({}, None) == {"cleaned": 1018816, "loaded": 1018816}
        assert "cleaned=1018816 loaded=1018816" in capsys.readouterr().out
        s3.download_file("lab", env["OUTPUT_KEY"], str(parquet.with_name("handler.parquet")))
    handler_rows = duckdb.sql(f"select * from read_parquet('{parquet.with_name('handler.parquet')}') except all "
                              f"select * from read_parquet('{parquet}')").fetchall()
    assert handler_rows == []
    assert count(connection) == 1018816
