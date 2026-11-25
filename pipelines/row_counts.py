import os

from pyspark.sql import SparkSession

TABLES = ["customers", "products", "orders", "order_items", "payments"]


def main() -> None:
    spark = SparkSession.builder.master("spark://spark-master:7077").appName("row-counts").getOrCreate()
    url = f"jdbc:postgresql://{os.environ['PGHOST']}:{os.environ['PGPORT']}/{os.environ['PGDATABASE']}"
    rows = [
        (
            table,
            spark.read.format("jdbc")
            .option("url", url)
            .option("dbtable", table)
            .option("user", os.environ["PGUSER"])
            .option("password", os.environ["PGPASSWORD"])
            .load()
            .count(),
        )
        for table in TABLES
    ]
    spark.createDataFrame(rows, "table string, rows long").coalesce(1).write.mode("overwrite").parquet("/lake/smoke/row_counts")
    spark.stop()


if __name__ == "__main__":
    main()
