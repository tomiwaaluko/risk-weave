"""Production observability: structured logging and latency metrics (RIS-33)."""

from __future__ import annotations

from .logging_config import configure_logging, get_request_id, scrub_secrets, set_request_id
from .metrics import latency_snapshot, latency_timer, record_latency

__all__ = [
    "configure_logging",
    "get_request_id",
    "scrub_secrets",
    "set_request_id",
    "latency_snapshot",
    "latency_timer",
    "record_latency",
]
