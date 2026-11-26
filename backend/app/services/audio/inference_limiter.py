"""Bounded concurrency for CPU inference (V1.1-C.2).

A single Basic Pitch job peaks around 262 MB, so N concurrent jobs cost roughly
N × 262 MB. This limiter makes the ceiling explicit and observable:

* ``max_concurrent_inferences`` slots (default 1)
* a bounded wait (``inference_queue_timeout_seconds``) before returning 503
* timing reported per job (queue wait + inference duration)

Honest limitation: a Python thread running ONNX inference cannot be pre-empted.
When a job exceeds ``inference_timeout_seconds`` we mark it failed, but the token
is only released after the underlying call actually returns - releasing earlier
would let a second job start while the first still holds the memory.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class InferenceBusy(RuntimeError):
    """Raised when no inference slot became free within the queue timeout."""

    def __init__(self, waited_seconds: float, limit: int) -> None:
        super().__init__("inference capacity exhausted")
        self.waited_seconds = waited_seconds
        self.limit = limit


@dataclass
class LimiterStats:
    capacity: int = 1
    active: int = 0
    queued: int = 0
    max_queued: int = 0
    completed: int = 0
    busied: int = 0
    timed_out: int = 0
    last_queue_wait: float = 0.0
    last_duration: float = 0.0
    recent: List[Dict[str, float]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "capacity": self.capacity,
            "active": self.active,
            "queued": self.queued,
            "max_queued": self.max_queued,
            "completed": self.completed,
            "busied": self.busied,
            "timed_out": self.timed_out,
            "last_queue_wait_seconds": round(self.last_queue_wait, 3),
            "last_inference_seconds": round(self.last_duration, 3),
        }


class InferenceLimiter:
    """Semaphore + queue accounting around one inference call."""

    def __init__(self, capacity: int = 1) -> None:
        self._capacity = max(1, int(capacity))
        self._semaphore = threading.BoundedSemaphore(self._capacity)
        self._lock = threading.Lock()
        self._stats = LimiterStats(capacity=self._capacity)

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def active(self) -> int:
        with self._lock:
            return self._stats.active

    def stats(self) -> Dict[str, object]:
        with self._lock:
            return self._stats.as_dict()

    @contextmanager
    def slot(self, timeout: float) -> Iterator[Dict[str, float]]:
        """Acquire a slot or raise :class:`InferenceBusy` after ``timeout``."""
        started = time.perf_counter()
        with self._lock:
            self._stats.queued += 1
            self._stats.max_queued = max(self._stats.max_queued, self._stats.queued)

        acquired = self._semaphore.acquire(timeout=max(0.0, timeout))
        waited = time.perf_counter() - started

        with self._lock:
            self._stats.queued -= 1
            if not acquired:
                self._stats.busied += 1
                logger.warning(
                    "inference capacity exhausted after %.1fs (capacity=%d)",
                    waited,
                    self._capacity,
                )
                raise InferenceBusy(waited, self._capacity)
            self._stats.active += 1
            self._stats.last_queue_wait = waited

        timings = {"queue_wait": waited, "duration": 0.0}
        finished = time.perf_counter()
        try:
            yield timings
        finally:
            timings["duration"] = finished - started - waited
            with self._lock:
                self._stats.active -= 1
                self._stats.completed += 1
                self._stats.last_duration = timings["duration"]
                self._stats.recent.append(
                    {"queue_wait": round(waited, 3), "duration": round(timings["duration"], 3)}
                )
                del self._stats.recent[:-20]
            self._semaphore.release()

    def mark_timeout(self) -> None:
        with self._lock:
            self._stats.timed_out += 1

    def reset(self) -> None:
        with self._lock:
            self._stats = LimiterStats(capacity=self._capacity)
        self._semaphore = threading.BoundedSemaphore(self._capacity)


_limiter: Optional[InferenceLimiter] = None
_limiter_lock = threading.Lock()


def get_limiter() -> InferenceLimiter:
    """Process-wide limiter sized from settings."""
    global _limiter
    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                from app.core.config import get_settings

                capacity = get_settings().max_concurrent_inferences
                _limiter = InferenceLimiter(capacity)
    return _limiter


def reset_limiter() -> None:
    """Drop the cached limiter (tests / settings reload)."""
    global _limiter
    with _limiter_lock:
        _limiter = None
