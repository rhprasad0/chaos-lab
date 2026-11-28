import pandas as pd
import pytest

import contract


def spec():
    return contract.load("input.yaml")


def frame(**renames):
    names = ["sheet"] + [c["name"] for c in spec()["columns"]]
    return pd.DataFrame({renames.get(name, name): [] for name in names})


def test_a_missing_column_names_the_columns_the_contract_does_not_list():
    with pytest.raises(contract.ContractError) as error:
        contract.check_input(frame(Price="UnitPrice"), spec())
    message = str(error.value)
    assert "rule=column_present column=Price rows=0 samples=[]" in message
    assert "unlisted_columns=['UnitPrice']" in message


def test_a_missing_column_without_extra_columns_gets_no_unlisted_part():
    broken = frame().drop(columns="Price")
    with pytest.raises(contract.ContractError) as error:
        contract.check_input(broken, spec())
    assert "rule=column_present column=Price rows=0 samples=[]" in str(error.value)
    assert "unlisted_columns" not in str(error.value)
