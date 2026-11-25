import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from pyspark.sql import SparkSession

PIPELINE = Path(__file__).resolve().parents[1] / "row_counts.py"
TABLES = ["customers", "products", "orders", "order_items", "payments"]


@pytest.fixture(scope="module")
def spark() -> Iterator[SparkSession]:
    session = SparkSession.builder.master("spark://spark-master:7077").appName("row-counts-test").config("spark.cores.max", "1").getOrCreate()
    yield session
    session.stop()


def source_count(spark: SparkSession, table: str) -> int:
    url = f"jdbc:postgresql://{os.environ['PGHOST']}:{os.environ['PGPORT']}/{os.environ['PGDATABASE']}"
    return (
        spark.read.format("jdbc")
        .option("url", url)
        .option("dbtable", table)
        .option("user", os.environ["PGUSER"])
        .option("password", os.environ["PGPASSWORD"])
        .load()
        .count()
    )


def run_pipeline() -> None:
    subprocess.run([sys.executable, str(PIPELINE)], check=True)


def test_row_counts_match_the_source_and_rerun_is_stable(spark: SparkSession) -> None:
    run_pipeline()
    first = spark.read.parquet("/lake/smoke/row_counts")
    assert [(f.name, f.dataType.simpleString()) for f in first.schema.fields] == [("table", "string"), ("rows", "bigint")]
    got = {r["table"]: r["rows"] for r in first.collect()}
    assert first.count() == 5
    assert got == {table: source_count(spark, table) for table in TABLES}

    run_pipeline()
    second = spark.read.parquet("/lake/smoke/row_counts")
    assert second.count() == 5
    assert {r["table"]: r["rows"] for r in second.collect()} == got
