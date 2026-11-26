"""Bounded inference concurrency (V1.1-C.2)."""

from __future__ import annotations

import threading
import time

import pytest

from app.services.audio.inference_limiter import InferenceBusy, InferenceLimiter


def test_capacity_is_enforced():
    limiter = InferenceLimiter(capacity=1)
    started = threading.Event()
    release = threading.Event()
    errors: list[Exception] = []

    def holder() -> None:
        try:
            with limiter.slot(timeout=1):
                started.set()
                release.wait(2)
        except Exception as exc:  # pragma: no cover - should not happen
            errors.append(exc)

    thread = threading.Thread(target=holder)
    thread.start()
    assert started.wait(2)

    with pytest.raises(InferenceBusy) as excinfo, limiter.slot(timeout=0.05):
        pass

    assert excinfo.value.limit == 1
    assert limiter.stats()["busied"] == 1

    release.set()
    thread.join()
    assert errors == []
    assert limiter.stats()["active"] == 0


def test_slot_is_released_after_success():
    limiter = InferenceLimiter(capacity=1)
    with limiter.slot(timeout=1) as timings:
        time.sleep(0.01)
    assert timings["duration"] >= 0
    assert limiter.stats()["active"] == 0
    assert limiter.stats()["completed"] == 1

    # the slot must be reusable
    with limiter.slot(timeout=1):
        pass
    assert limiter.stats()["completed"] == 2


def test_slot_is_released_when_the_body_raises():
    limiter = InferenceLimiter(capacity=1)
    with pytest.raises(RuntimeError), limiter.slot(timeout=1):
        raise RuntimeError("inference blew up")
    assert limiter.stats()["active"] == 0
    with limiter.slot(timeout=1):
        pass  # no deadlock


def test_queue_wait_is_recorded():
    limiter = InferenceLimiter(capacity=1)
    with limiter.slot(timeout=1), pytest.raises(InferenceBusy), limiter.slot(timeout=0.05):
        pass
    stats = limiter.stats()
    assert stats["max_queued"] >= 1


def test_timeout_counter():
    limiter = InferenceLimiter(capacity=1)
    limiter.mark_timeout()
    assert limiter.stats()["timed_out"] == 1


def test_capacity_never_below_one():
    assert InferenceLimiter(capacity=0).capacity == 1
    assert InferenceLimiter(capacity=-5).capacity == 1


def test_reset_clears_stats():
    limiter = InferenceLimiter(capacity=2)
    with limiter.slot(timeout=1):
        pass
    limiter.reset()
    stats = limiter.stats()
    assert stats["completed"] == 0
    assert stats["capacity"] == 2


def test_get_limiter_is_process_wide(monkeypatch):
    from app.services.audio import inference_limiter

    inference_limiter.reset_limiter()
    first = inference_limiter.get_limiter()
    second = inference_limiter.get_limiter()
    assert first is second
    assert first.capacity >= 1
    inference_limiter.reset_limiter()
