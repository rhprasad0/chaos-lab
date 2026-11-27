import logging
from contextlib import contextmanager

log = logging.getLogger("retail_etl")


class PipelineError(Exception):
    def __init__(self, step, message):
        super().__init__(message)
        self.step = step


@contextmanager
def step(name):
    try:
        yield
    except PipelineError as exc:
        log.error("step=%s failed: %s", exc.step, exc)
        raise
    except Exception as exc:
        log.error("step=%s failed: %s: %s", name, type(exc).__name__, exc)
        raise
