import sys
import uuid
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "retail_etl"))


@pytest.fixture
def db_schema(monkeypatch):
    name = f"t_{uuid.uuid4().hex[:12]}"
    monkeypatch.setenv("DB_SCHEMA", name)
    yield name
    with psycopg.connect("", autocommit=True) as connection:
        connection.execute(f"drop schema if exists {name} cascade")
