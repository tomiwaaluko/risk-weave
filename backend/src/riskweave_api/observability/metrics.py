"""In-process latency histograms for the §15 evaluation metrics (RIS-33).

Tracks scenario-parse, propagation-recompute (slider round trip and REST
`/run`), and explanation-generation latency so production p50/p95 can be
checked against the `RW-NFR-002` 500 ms recompute budget and fed into the
RIS-21 evaluation dashboard. Deliberately in-process and dependency-free
(no Prometheus/Grafana — out of scope per the ticket) since this is a single
demo-scale replica (`RW-NFR-005`); a bounded ring buffer keeps memory flat.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from types import TracebackType

_MAX_SAMPLES = 1000

#: Canonical histogram names — the RIS-21 dashboard reads these from `/metrics/latency`.
SCENARIO_PARSE = "scenario_parse"
PROPAGATION_RECOMPUTE = "propagation_recompute"
EXPLANATION_GENERATION = "explanation_generation"


@dataclass
class _Histogram:
    samples: list[float] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def observe(self, value_ms: float) -> None:
        with self._lock:
            self.samples.append(value_ms)
            if len(self.samples) > _MAX_SAMPLES:
                del self.samples[: len(self.samples) - _MAX_SAMPLES]

    def snapshot(self) -> dict[str, float | int | None]:
        with self._lock:
            samples = sorted(self.samples)
        if not samples:
            return {"count": 0, "p50_ms": None, "p95_ms": None, "max_ms": None}

        def percentile(p: float) -> float:
            index = min(len(samples) - 1, int(len(samples) * p))
            return round(samples[index], 2)

        return {
            "count": len(samples),
            "p50_ms": percentile(0.50),
            "p95_ms": percentile(0.95),
            "max_ms": round(samples[-1], 2),
        }


_histograms: dict[str, _Histogram] = {}
_histograms_lock = Lock()


def _get_histogram(name: str) -> _Histogram:
    with _histograms_lock:
        histogram = _histograms.get(name)
        if histogram is None:
            histogram = _Histogram()
            _histograms[name] = histogram
        return histogram


def record_latency(name: str, value_ms: float) -> None:
    _get_histogram(name).observe(value_ms)


def latency_snapshot() -> dict[str, dict[str, float | int | None]]:
    """A snapshot per named histogram, for the `/metrics/latency` endpoint."""
    with _histograms_lock:
        names = list(_histograms.keys())
    return {name: _get_histogram(name).snapshot() for name in names}


def reset_metrics() -> None:
    """Test-only: clear all recorded samples between test cases."""
    with _histograms_lock:
        _histograms.clear()


class latency_timer:
    """Context manager recording elapsed wall time into a named histogram.

    Usage: ``with latency_timer(SCENARIO_PARSE): parser.parse_freeform(text)``
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._start = 0.0

    def __enter__(self) -> latency_timer:
        self._start = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        record_latency(self._name, (time.perf_counter() - self._start) * 1000.0)
