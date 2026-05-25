"""Structured logging setup.

Uses `structlog` so LLM request/response logs come out as JSON in production
and human-readable text during development.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from aiops_agent.config import LogLevel


def configure_logging(level: LogLevel = "INFO", *, json_output: bool = False) -> None:
    """Configure structlog + stdlib logging.

    Args:
        level: Minimum log level to emit.
        json_output: If True, render logs as JSON (production); otherwise
            render as colored key-value text (development).
    """
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, level),
    )

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a configured structlog logger."""
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
