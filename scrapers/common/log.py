# Copyright (c) 2026 Venture Hunt. All rights reserved.
# Proprietary and confidential. See LICENSE.
"""Structured JSON logging for scraper runs (one event per line on stderr)."""

import logging
import sys
from typing import cast

import structlog
from structlog.typing import FilteringBoundLogger


def configure_logging() -> None:
    """Configure structlog for ISO-timestamped JSON events on stderr."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(source: str) -> FilteringBoundLogger:
    """Return a logger bound to one scraper source.

    Args:
        source: The scraper source name ('github', 'papers.arxiv').

    Returns:
        A bound structlog logger.
    """
    logger: object = structlog.get_logger(source=source)
    return cast("FilteringBoundLogger", logger)
