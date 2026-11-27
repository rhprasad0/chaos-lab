import logging

from .clean import clean
from .extract import read_workbook
from .load import check_table, replace_table, write_parquet

log = logging.getLogger("retail_etl")


class StepError(Exception):
    def __init__(self, step, error):
        super().__init__(f"{step}: {error}")
        self.step = step


class step:
    def __init__(self, name):
        self.name = name

    def __enter__(self):
        return self

    def __exit__(self, kind, error, trace):
        if error is None or isinstance(error, StepError):
            return False
        reason = " ".join(f"{kind.__name__}: {error}".split())
        log.error("ETL step %s failed: %s", self.name, reason)
        raise StepError(self.name, reason) from error


def run(workbook_path, parquet_path, connect, publish=lambda path: None):
    report = {}
    with step("extract"):
        first, second = read_workbook(workbook_path)
        report["raw_rows"] = len(first) + len(second)
    with step("clean"):
        rows, report["outcomes"] = clean(first, second)
    with step("write"):
        write_parquet(rows, parquet_path)
        publish(parquet_path)
    with step("load"):
        with connect() as connection:
            with connection.transaction():
                cursor = connection.cursor()
                expected = replace_table(cursor, parquet_path)
                with step("check"):
                    report["checks"] = check_table(cursor, expected)
    report["loaded_rows"] = expected
    log.info("ETL complete: %s", report)
    return report
