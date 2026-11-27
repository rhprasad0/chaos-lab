import json
import logging
import os

import boto3
from psycopg.conninfo import make_conninfo

from .pipeline import StepError, run

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _conninfo():
    host, port, user = os.environ["DB_HOST"], int(os.environ.get("DB_PORT", "5432")), os.environ["DB_USER"]
    token = boto3.client("rds").generate_db_auth_token(DBHostname=host, Port=port, DBUsername=user)
    return make_conninfo(
        host=host, port=port, user=user, dbname=os.environ["DB_NAME"], password=token, sslmode="require"
    )


def handler(event, context):
    try:
        result = run(
            os.environ["INPUT_URI"],
            os.environ["OUTPUT_URI"],
            _conninfo(),
            os.environ["DB_SCHEMA"],
        )
    except StepError as error:
        logger.error("ETL FAILED %s", error)
        raise
    except Exception as error:
        logger.error("ETL FAILED step=setup failed: %s: %s", type(error).__name__, " ".join(str(error).split()))
        raise
    logger.info("ETL OK %s", json.dumps(result))
    return result
