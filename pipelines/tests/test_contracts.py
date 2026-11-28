import pandas as pd
import psycopg
import pytest

import contract
import etl

SHEETS = ("Year 2009-2010", "Year 2010-2011")


def frame(rows=10):
    sheets = [SHEETS[i % 2] for i in range(rows)]
    return pd.DataFrame(
        {
            "sheet": sheets,
            "Invoice": [f"{500000 + i}" for i in range(rows)],
            "StockCode": ["85123A"] * rows,
            "Description": pd.array(["MUG"] * (rows - 1) + [None], dtype="str"),
            "Quantity": pd.array(range(1, rows + 1), dtype="Int64"),
            "InvoiceDate": pd.to_datetime(["2010-06-01 10:00"] * rows),
            "Price": [2.5] * rows,
            "Customer ID": pd.array([17850] * (rows - 1) + [None], dtype="Int64"),
            "Country": ["United Kingdom"] * rows,
        }
    )


def small_input(rows):
    spec = contract.load("input.yaml")
    spec["row_count"] = {"expected": rows, "tolerance": 0.02}
    return spec


def test_input_contract_accepts_a_clean_frame():
    contract.check_input(frame(), small_input(10))


def test_input_contract_names_rule_column_rows_and_samples():
    bad = frame().rename(columns={"Price": "UnitPrice"})
    bad.loc[[2, 3, 4, 5], "Invoice"] = None
    bad = bad[bad["sheet"] == SHEETS[0]]
    with pytest.raises(contract.ContractError) as error:
        contract.check_input(bad, small_input(5))
    message = str(error.value)
    assert "rule=column_present column=Price" in message
    assert "rule=not_null column=Invoice rows=2 samples=['row 2', 'row 4']" in message
    assert "rule=sheet_present column=sheet rows=0 samples=['Year 2010-2011']" in message
    assert "rule=row_count:5+-2% column=*" not in message


def test_input_contract_checks_types_range_and_row_count():
    bad = frame()
    bad["Quantity"] = [1.5] * 10
    bad.loc[0, "InvoiceDate"] = pd.Timestamp("2012-01-01")
    with pytest.raises(contract.ContractError) as error:
        contract.check_input(bad, small_input(100))
    message = str(error.value)
    assert "rule=type:integer column=Quantity rows=10" in message
    assert "rule=range:2009-12-01..2011-12-10 column=InvoiceDate rows=1 samples=['2012-01-01 00:00:00']" in message
    assert "rule=row_count:100+-2% column=* rows=10" in message


@pytest.fixture
def cur(db_schema):
    with psycopg.connect("") as connection, connection.cursor() as cursor:
        cursor.execute(etl.TABLE.format(schema=db_schema))
        yield cursor, db_schema


def small_output(rows, total):
    spec = contract.load("output.yaml")
    spec["row_count"] = {"expected": rows, "tolerance": 0.01}
    spec["sum"] = {"expression": "quantity * price", "expected": total, "tolerance": 0.01}
    return spec


def test_output_contract_accepts_a_clean_table(cur):
    cursor, schema = cur
    cursor.execute(f"insert into {schema}.transactions values ('1','A','x',2,'2010-01-01',1.5,1,'UK',false), ('C2','A','x',-1,'2010-01-01',1.5,null,'UK',true)")
    contract.check_output(cursor, schema, small_output(2, 1.5), 2)


def test_output_contract_names_the_violation(cur):
    cursor, schema = cur
    cursor.execute(
        f"insert into {schema}.transactions values "
        f"('1','A','x',2,'2010-01-01',1.5,1,'UK',true), ('1','A','x',2,'2010-01-01',1.5,1,'UK',true), "
        f"(null,'A','x',2,'2010-01-01',1.5,1,'UK',false)"
    )
    with pytest.raises(contract.ContractError) as error:
        contract.check_output(cursor, schema, small_output(3, 9), 5)
    message = str(error.value)
    assert "rule=not_null column=invoice rows=1" in message
    assert "rule=no_duplicates column=* rows=1" in message
    assert "rule=cancellation_flag column=is_cancellation rows=3 samples=['1=True', '1=True', 'None=False']" in message
    assert "rule=row_count_equals_parquet" in message
