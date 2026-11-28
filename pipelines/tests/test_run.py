import hashlib

import boto3
import duckdb
import pandas as pd
import psycopg
import pytest
from moto import mock_aws

import contract
import etl

BUCKET = "lab"
INPUT_KEY = "in/workbook.xlsx"
OUTPUT_KEY = "out/clean.parquet"
WORKBOOK = b"not really a workbook"
GOOD = [
    ("1001", "85123A", "MUG", 2, "2010-06-01 10:00:00", 2.5, 17850, "United Kingdom", False),
    ("C1002", "85123A", "MUG", -1, "2010-06-02 10:00:00", 2.5, 17850, "United Kingdom", True),
]
BAD = [("C1003", "85123A", "MUG", 1, "2010-06-03 10:00:00", 2.5, 17850, "United Kingdom", False)]


def input_frame():
    return pd.DataFrame(
        {
            "sheet": ["Year 2009-2010", "Year 2010-2011"],
            "Invoice": ["1001", "C1002"],
            "StockCode": ["85123A", "85123A"],
            "Description": ["MUG", "MUG"],
            "Quantity": pd.array([2, -1], dtype="Int64"),
            "InvoiceDate": pd.to_datetime(["2010-06-01 10:00", "2010-06-02 10:00"]),
            "Price": [2.5, 2.5],
            "Customer ID": pd.array([17850, 17850], dtype="Int64"),
            "Country": ["United Kingdom"] * 2,
        }
    )


@pytest.fixture
def env(monkeypatch, tmp_path, db_schema):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("BUCKET", BUCKET)
    monkeypatch.setenv("INPUT_KEY", INPUT_KEY)
    monkeypatch.setenv("OUTPUT_KEY", OUTPUT_KEY)
    for name, rows, total in (("input.yaml", 2, None), ("output.yaml", 2, 2.5)):
        spec = contract.load(name)
        spec["row_count"] = {"expected": rows, "tolerance": 0.01}
        if total:
            spec["sum"] = {"expression": "quantity * price", "expected": total, "tolerance": 0.01}
        (tmp_path / name).write_text(__import__("yaml").safe_dump(spec))
    monkeypatch.setattr(contract, "DIRECTORY", tmp_path)
    monkeypatch.setattr(etl, "parse_workbook", lambda path: input_frame())
    monkeypatch.setattr(etl, "database", lambda: psycopg.connect(""))
    with mock_aws():
        s3 = boto3.client("s3")
        s3.create_bucket(Bucket=BUCKET)
        s3.put_bucket_versioning(Bucket=BUCKET, VersioningConfiguration={"Status": "Enabled"})
        version = s3.put_object(Bucket=BUCKET, Key=INPUT_KEY, Body=WORKBOOK)["VersionId"]
        yield s3, version, db_schema


def transform_to(monkeypatch, rows):
    def transform(workbook, parquet):
        duckdb.sql(
            "copy (select * from (values "
            + ", ".join(str(row).replace("False", "false").replace("True", "true") for row in rows)
            + ") t(invoice, stock_code, description, quantity, invoice_date, price, customer_id, country, is_cancellation)) "
            f"to '{parquet}' (format parquet)"
        )
        return len(rows)

    monkeypatch.setattr(etl, "transform", transform)


def table_rows(schema):
    with psycopg.connect("") as connection:
        return connection.execute(f"select invoice from {schema}.transactions order by invoice").fetchall()


def ledger(schema):
    with psycopg.connect("") as connection, connection.cursor(row_factory=psycopg.rows.dict_row) as cur:
        cur.execute(f"select * from {schema}.etl_runs order by started_at")
        return cur.fetchall()


def test_successful_run_is_recorded_with_the_input_version(env, monkeypatch):
    s3, version, schema = env
    transform_to(monkeypatch, GOOD)

    result = etl.handler({}, type("Context", (), {"aws_request_id": "req-1"})())

    assert result == {"cleaned": 2, "loaded": 2}
    assert table_rows(schema) == [("1001",), ("C1002",)]
    assert s3.head_object(Bucket=BUCKET, Key=OUTPUT_KEY)["ContentLength"] > 0
    [row] = ledger(schema)
    assert (row["run_id"], row["status"], row["failed_step"], row["error"]) == ("req-1", "succeeded", None, None)
    assert row["input_version_id"] == version
    assert row["input_sha256"] == hashlib.sha256(WORKBOOK).hexdigest()
    assert (row["rows_extracted"], row["rows_cleaned"], row["rows_loaded"]) == (2, 2, 2)
    assert row["code_version"] == "unknown"
    assert row["started_at"] <= row["ended_at"]


def test_failed_output_contract_leaves_output_and_table_unchanged(env, monkeypatch, caplog):
    s3, version, schema = env
    transform_to(monkeypatch, GOOD)
    etl.handler({}, None)
    published = s3.get_object(Bucket=BUCKET, Key=OUTPUT_KEY)["Body"].read()

    transform_to(monkeypatch, GOOD + BAD)
    with pytest.raises(contract.ContractError):
        etl.handler({}, None)

    assert "step=output_contract failed" in caplog.text
    assert s3.get_object(Bucket=BUCKET, Key=OUTPUT_KEY)["Body"].read() == published
    assert table_rows(schema) == [("1001",), ("C1002",)]
    first, second = ledger(schema)
    assert first["status"] == "succeeded"
    assert second["status"] == "failed"
    assert second["failed_step"] == "output_contract"
    assert "cancellation_flag" in second["error"]
    assert (second["rows_cleaned"], second["rows_loaded"]) == (3, None)
    assert second["input_version_id"] == version


def test_failed_input_contract_stops_before_transform_and_is_recorded(env, monkeypatch, caplog):
    s3, version, schema = env
    monkeypatch.setattr(etl, "parse_workbook", lambda path: input_frame().rename(columns={"Price": "UnitPrice"}))
    monkeypatch.setattr(etl, "transform", lambda *args: pytest.fail("transform ran"))

    with pytest.raises(contract.ContractError):
        etl.handler({}, None)

    assert "step=input_contract failed: ContractError: input contract violated: rule=column_present column=Price" in caplog.text
    with pytest.raises(s3.exceptions.ClientError):
        s3.head_object(Bucket=BUCKET, Key=OUTPUT_KEY)
    [row] = ledger(schema)
    assert (row["status"], row["failed_step"], row["rows_extracted"]) == ("failed", "input_contract", 2)
