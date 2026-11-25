import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from pyspark.sql import SparkSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "generator"))

import retail  # noqa: E402


@pytest.fixture(scope="module")
def spark() -> Iterator[SparkSession]:
    session = (
        SparkSession.builder.master("spark://spark-master:7077")
        .appName("lab-smoke")
        .config("spark.executor.memory", "1g")
        .getOrCreate()
    )
    yield session
    session.stop()


def read(spark: SparkSession, table: str):
    url = f"jdbc:postgresql://{os.environ['PGHOST']}:{os.environ['PGPORT']}/{os.environ['PGDATABASE']}"
    return (
        spark.read.format("jdbc")
        .option("url", url)
        .option("dbtable", table)
        .option("user", os.environ["PGUSER"])
        .option("password", os.environ["PGPASSWORD"])
        .load()
    )


def test_cluster_reads_the_seeded_source_and_writes_parquet_to_the_lake(spark: SparkSession) -> None:
    expected = retail.generate(int(os.environ.get("LAB_SEED", "1")))
    for table, rows in expected.items():
        assert read(spark, table).count() == len(rows), table
    read(spark, "orders").write.mode("overwrite").parquet("/lake/smoke/orders")
    assert spark.read.parquet("/lake/smoke/orders").count() == len(expected["orders"])
    workers = spark.sparkContext._jsc.sc().getExecutorMemoryStatus().size() - 1
    assert workers >= 1
