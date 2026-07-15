from __future__ import annotations

import threading
import time
from collections.abc import Callable


class RateLimiter:
    """Thread-safe evenly spaced limiter; ten requests/sec means one each 100 ms."""

    def __init__(
        self,
        requests_per_second: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self._interval = 1 / requests_per_second
        self._clock = clock
        self._sleep = sleep
        self._next_at = clock()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            if now < self._next_at:
                self._sleep(self._next_at - now)
                now = self._clock()
            self._next_at = max(now, self._next_at) + self._interval
