"""Structured JSON logging for the Railway deployment (RIS-33).

Every log line is a single JSON object (timestamp, level, logger, message,
plus request-scoped fields) so Railway's log viewer and any downstream log
drain can filter/alert on structured keys instead of parsing prose. All
formatted output is passed through :func:`scrub_secrets` first, satisfying
`RW-SEC-001` ("no secrets ... in logs") regardless of what a caller logs.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

# Field names that must never appear in cleartext in a log payload, even if a
# caller passes them in `extra={"fields": {...}}` by mistake.
_SECRET_FIELD_NAMES = frozenset(
    {
        "authorization",
        "api_key",
        "gemini_api_key",
        "fred_api_key",
        "riskweave_api_key",
        "password",
        "neo4j_password",
        "database_url",
        "redis_url",
        "neo4j_uri",
        "secret",
        "token",
    }
)

# Patterns scrubbed out of free-text log messages and exception text: bearer
# tokens, credentials embedded in connection URLs (postgres://user:pass@host,
# redis://:pass@host, bolt://user:pass@host), and key=value/json-style secrets.
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-_.]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(://[^:/\s@]+:)[^@\s]+(@)"), r"\1[REDACTED]\2"),
    (
        re.compile(
            r"((?:api[_-]?key|password|secret|token)[\"']?\s*[:=]\s*[\"']?)"
            r"[^\s,&\"'}]+",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]",
    ),
)


def scrub_secrets(text: str) -> str:
    """Redact anything matching a known credential shape (`RW-SEC-001`)."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def set_request_id(request_id: str | None) -> None:
    _request_id.set(request_id)


def get_request_id() -> str | None:
    return _request_id.get()


class JsonFormatter(logging.Formatter):
    """Renders each :class:`logging.LogRecord` as one scrubbed JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub_secrets(record.getMessage()),
        }

        request_id = get_request_id()
        if request_id is not None:
            payload["request_id"] = request_id

        for key, value in getattr(record, "fields", {}).items():
            if key.lower() in _SECRET_FIELD_NAMES:
                payload[key] = "[REDACTED]"
            elif isinstance(value, str):
                payload[key] = scrub_secrets(value)
            else:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = scrub_secrets(self.formatException(record.exc_info))

        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None) -> None:
    """Install the JSON formatter on the root logger. Idempotent.

    Safe to call more than once (e.g. once at import time and once in the
    FastAPI lifespan under test) — it replaces rather than stacks handlers.
    """
    resolved_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()

    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(resolved_level)
