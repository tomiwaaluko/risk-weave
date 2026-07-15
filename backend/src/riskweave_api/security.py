"""API-key auth and per-IP rate limiting for the public deployment (RIS-31, ADR-010).

Enabling infrastructure only — no propagation math, no Gemini calls. The API
key gate and the token buckets below decide *whether* a request proceeds;
they never touch a weight, ratio, or explanation.
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

from fastapi import HTTPException, Request, WebSocket, status


def client_ip(request: Request | WebSocket) -> str:
    """Best-effort per-client key for rate limiting.

    Railway terminates TLS at its edge and sets ``X-Forwarded-For``; trust its
    first hop for the real client address, falling back to the ASGI socket
    peer for local/dev runs where no proxy is in front of the app.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


def require_api_key(request: Request) -> None:
    """Reject requests missing the shared bearer key on gated endpoints.

    A deployment with no ``RISKWEAVE_API_KEY`` configured (local dev, CI, the
    Docker Compose stack) stays open, matching today's behavior there — this
    only takes effect once an operator sets the key, which Railway production
    does (`RW-SEC-001`).
    """
    settings = request.app.state.settings
    configured = settings.api_key
    if configured is None:
        return

    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if (
        scheme.lower() != "bearer"
        or not token
        or not secrets.compare_digest(token, configured.get_secret_value())
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")


@dataclass
class TokenBucket:
    capacity: float
    refill_per_sec: float
    tokens: float = field(init=False)
    updated: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = self.capacity
        self.updated = time.monotonic()

    def consume(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.updated
        self.updated = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


class RateLimiter:
    """In-memory per-(bucket, ip) token bucket.

    One process, one demo-scale deployment (`RW-NFR-005`); no distributed
    store required. A fresh instance lives on ``app.state`` for the lifespan
    of the process, so it resets on redeploy like any other in-memory state.
    """

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], TokenBucket] = {}

    def allow(self, name: str, ip: str, capacity: float, refill_per_sec: float) -> bool:
        key = (name, ip)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(capacity=capacity, refill_per_sec=refill_per_sec)
            self._buckets[key] = bucket
        return bucket.consume()


def _rate_limit_dependency(name: str, capacity: float, refill_per_sec: float):
    def _dependency(request: Request) -> None:
        settings = request.app.state.settings
        if not settings.rate_limit_enabled:
            return
        limiter: RateLimiter = request.app.state.rate_limiter
        if not limiter.allow(name, client_ip(request), capacity, refill_per_sec):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate limited"
            )

    return _dependency


# Tight budget for Gemini-calling endpoints: burst of 5, sustained ~5/minute —
# enough for a live demo click-through, nowhere near enough to run up a bill.
gemini_rate_limit = _rate_limit_dependency("gemini", capacity=5, refill_per_sec=5 / 60)

# Loose budget for other mutating/compute endpoints: burst of 30, ~60/minute sustained.
default_rate_limit = _rate_limit_dependency("default", capacity=30, refill_per_sec=1.0)

# WebSocket connection cap (RW-NFR-002's 500 ms recompute budget only helps
# if a connection can't flood recomputes) and per-connection message throttle.
MAX_SLIDER_CONNECTIONS = 200
SLIDER_MESSAGE_BUCKET_CAPACITY = 20
SLIDER_MESSAGE_BUCKET_REFILL_PER_SEC = 10.0


def new_slider_message_bucket() -> TokenBucket:
    """A fresh per-connection throttle; call once per accepted WebSocket."""
    return TokenBucket(
        capacity=SLIDER_MESSAGE_BUCKET_CAPACITY,
        refill_per_sec=SLIDER_MESSAGE_BUCKET_REFILL_PER_SEC,
    )


def try_reserve_slider_connection(app_state) -> bool:
    """Claim one of ``MAX_SLIDER_CONNECTIONS`` global connection slots.

    Demo-scale, single-process cap — anonymous clients can otherwise open
    unlimited WebSocket connections, each driving recomputes.
    """
    current = getattr(app_state, "slider_connections", 0)
    if current >= MAX_SLIDER_CONNECTIONS:
        return False
    app_state.slider_connections = current + 1
    return True


def release_slider_connection(app_state) -> None:
    current = getattr(app_state, "slider_connections", 0)
    app_state.slider_connections = max(0, current - 1)
