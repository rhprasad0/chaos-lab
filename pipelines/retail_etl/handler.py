import logging
import os
import tempfile

import boto3
import psycopg

from .pipeline import run

logging.getLogger().setLevel(logging.INFO)


def connect():
    host = os.environ["DB_HOST"]
    port = int(os.environ["DB_PORT"])
    user = os.environ["DB_USER"]
    token = boto3.client("rds").generate_db_auth_token(DBHostname=host, Port=port, DBUsername=user)
    return psycopg.connect(
        host=host,
        port=port,
        user=user,
        password=token,
        dbname=os.environ["DB_NAME"],
        sslmode="require",
    )


def handler(event, context):
    with tempfile.TemporaryDirectory(dir="/tmp") as workdir:
        return run(
            os.environ["SOURCE_URI"],
            os.environ["TARGET_URI"],
            os.environ["DB_SCHEMA"],
            connect,
            workdir,
        )
