"""Structured JSON logs: one event per line, appended to the log file."""
from pathlib import Path
from typing import TextIO

import structlog


def configure(path: Path | None = None, stream: TextIO | None = None) -> None:
    """Log JSON lines to `stream` (tests) or append to `path`."""
    if stream is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = open(path, "a", buffering=1)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.WriteLoggerFactory(file=stream),
        cache_logger_on_first_use=False,
    )


def get(**context):
    return structlog.get_logger().bind(**context)
