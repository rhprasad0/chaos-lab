import logging

from .clean import clean
from .errors import step
from .extract import extract
from .load import load
from .write import write_parquet

log = logging.getLogger("retail_etl")


def run(connect, fetch, publish, parquet_path):
    with step("extract"):
        sheets = extract(fetch())
    with step("clean"):
        kept, counts = clean(sheets)
    with step("write"):
        write_parquet(kept, parquet_path)
        publish(parquet_path)
    with step("load"):
        checks = load(connect, parquet_path)
    summary = {"raw_rows": sum(map(len, sheets)), "outcomes": counts, "checks": checks}
    log.info("etl succeeded: %s", summary)
    return summary
