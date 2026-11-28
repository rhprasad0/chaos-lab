from pathlib import Path

import pandas as pd
import yaml

DIRECTORY = Path(__file__).parent / "contracts"
SAMPLES = 3


class ContractError(RuntimeError):
    pass


def load(name):
    return yaml.safe_load((DIRECTORY / name).read_text())


def violation(rule, column, rows, samples):
    shown = [str(sample) for sample in list(samples)[:SAMPLES]]
    return f"rule={rule} column={column} rows={rows} samples={shown}"


def raise_if(problems, name):
    if problems:
        raise ContractError(f"{name} violated: " + "; ".join(problems))


def tolerates(actual, spec):
    expected = spec["expected"]
    return abs(actual - expected) <= expected * spec["tolerance"]


TYPE_CHECKS = {
    "text": lambda s: pd.api.types.infer_dtype(s, skipna=True) in ("string", "empty"),
    "integer": pd.api.types.is_integer_dtype,
    "timestamp": pd.api.types.is_datetime64_any_dtype,
    "decimal": lambda s: pd.api.types.is_float_dtype(s) or pd.api.types.is_integer_dtype(s),
}


def check_input(frame, contract):
    problems = []
    if "sheet" in frame:
        present = set(frame["sheet"])
        for sheet in contract["sheets"]:
            if sheet not in present:
                problems.append(violation("sheet_present", "sheet", 0, [sheet]))
    else:
        problems.append(violation("sheet_present", "sheet", len(frame), contract["sheets"]))
    for column in contract["columns"]:
        name = column["name"]
        if name not in frame:
            problems.append(violation("column_present", name, len(frame), []))
            continue
        values = frame[name]
        filled = values.dropna()
        if not TYPE_CHECKS[column["type"]](values):
            problems.append(violation(f"type:{column['type']}", name, len(filled), filled))
        if not column["nullable"]:
            missing = values[values.isna()]
            if len(missing):
                problems.append(violation("not_null", name, len(missing), [f"row {i}" for i in missing.index]))
    for rule in contract["ranges"]:
        name = rule["column"]
        if name not in frame or not pd.api.types.is_datetime64_any_dtype(frame[name]):
            continue
        low, high = pd.Timestamp(rule["min"]), pd.Timestamp(rule["max"]) + pd.Timedelta(days=1)
        outside = frame[name][(frame[name] < low) | (frame[name] >= high)]
        if len(outside):
            problems.append(violation(f"range:{rule['min']}..{rule['max']}", name, len(outside), outside))
    if not tolerates(len(frame), contract["row_count"]):
        spec = contract["row_count"]
        problems.append(violation(f"row_count:{spec['expected']}+-{spec['tolerance']:.0%}", "*", len(frame), [len(frame)]))
    raise_if(problems, "input contract")


def check_output(cur, schema, contract, parquet_rows):
    table = f"{schema}.{contract['table']}"
    problems = []
    cur.execute(
        "select a.attname, format_type(a.atttypid, a.atttypmod) from pg_attribute a "
        "where a.attrelid = %s::regclass and a.attnum > 0 and not a.attisdropped",
        (table,),
    )
    types = dict(cur.fetchall())
    present = []
    for column in contract["columns"]:
        name = column["name"]
        if name not in types:
            problems.append(violation("column_present", name, 0, []))
        elif types[name] != column["type"]:
            problems.append(violation(f"type:{column['type']}", name, 0, [types[name]]))
        else:
            present.append(column)
    for column in present:
        name = column["name"]
        if column["nullable"]:
            continue
        cur.execute(f"select count(*) from {table} where {name} is null")
        nulls = cur.fetchone()[0]
        if nulls:
            cur.execute(f"select t::text from {table} t where {name} is null limit {SAMPLES}")
            problems.append(violation("not_null", name, nulls, [row[0] for row in cur.fetchall()]))
    names = ", ".join(c["name"] for c in contract["columns"] if c["name"] in types)
    cur.execute(f"select coalesce(sum(n - 1), 0) from (select count(*) n from {table} group by {names} having count(*) > 1) d")
    duplicates = cur.fetchone()[0]
    if duplicates:
        cur.execute(f"select t::text from (select {names} from {table} group by {names} having count(*) > 1) t limit {SAMPLES}")
        problems.append(violation("no_duplicates", "*", duplicates, [row[0] for row in cur.fetchall()]))
    cur.execute(f"select count(*) from {table}")
    loaded = cur.fetchone()[0]
    if loaded != parquet_rows:
        problems.append(violation("row_count_equals_parquet", "*", loaded, [f"table {loaded}", f"parquet {parquet_rows}"]))
    spec = contract["row_count"]
    for where, count in (("table", loaded), ("parquet", parquet_rows)):
        if not tolerates(count, spec):
            problems.append(violation(f"row_count:{spec['expected']}+-{spec['tolerance']:.0%}", where, count, [count]))
    spec = contract["sum"]
    cur.execute(f"select coalesce(sum({spec['expression']}), 0) from {table}")
    total = float(cur.fetchone()[0])
    if not tolerates(total, spec):
        problems.append(violation(f"sum:{spec['expected']}+-{spec['tolerance']:.0%}", spec["expression"], loaded, [total]))
    flag = contract["cancellation"]
    cur.execute(
        f"select count(*) from {table} where {flag['column']} is distinct from starts_with({flag['key']}, %s)",
        (flag["prefix"],),
    )
    wrong = cur.fetchone()[0]
    if wrong:
        cur.execute(
            f"select {flag['key']}, {flag['column']} from {table} "
            f"where {flag['column']} is distinct from starts_with({flag['key']}, %s) limit {SAMPLES}",
            (flag["prefix"],),
        )
        problems.append(violation("cancellation_flag", flag["column"], wrong, [f"{k}={v}" for k, v in cur.fetchall()]))
    raise_if(problems, "output contract")
