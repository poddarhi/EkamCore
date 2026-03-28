"""Structured JSON logging configuration for EkamCore API."""

import logging
import sys

import structlog

from api.config import settings


def configure_logging() -> None:
    """Configure structlog for JSON output with ISO timestamps."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set the root logger level so filter_by_level works
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)
