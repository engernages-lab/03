"""Singleton manager for the Basic Pitch model (V1.1-C.2).

Why this exists: ``basic_pitch.inference.run_inference`` builds a new ``Model``
whenever it is handed a *path* (see the upstream source), so every request used
to rebuild the ONNX session. Measured cost is small (~30–70 ms) but it is pure
waste and it churns the ORT arena. This module owns exactly one instance per
process, exposes its lifecycle for ``/ready``, and records timing so the
deployment report can quote real numbers instead of guesses.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ModelState:
    """Observable lifecycle of the shared model."""

    status: str = "not_loaded"  # not_loaded | loading | ready | failed | unavailable
    error: Optional[str] = None
    load_seconds: Optional[float] = None
    warmup_seconds: Optional[float] = None
    loaded_at: Optional[float] = None
    model_id: str = "basic_pitch"
    model_version: Optional[str] = None
    runtime: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "error": self.error,
            "load_seconds": self.load_seconds,
            "warmup_seconds": self.warmup_seconds,
            "loaded_at": self.loaded_at,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "runtime": self.runtime,
            **({"extra": self.extra} if self.extra else {}),
        }


class ModelManager:
    """Thread-safe holder for the process-wide Basic Pitch model."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model: Any = None
        self._state = ModelState()
        self._inference_calls = 0

    # -- lifecycle ---------------------------------------------------------
    def load(self, *, warmup: bool = False) -> ModelState:
        """Load the model once. Concurrent callers wait for the same result."""
        with self._lock:
            if self._state.status == "ready":
                return self._state
            if self._state.status == "unavailable":
                return self._state

            self._state = ModelState(status="loading")
            started = time.perf_counter()
            try:
                from basic_pitch import ICASSP_2022_MODEL_PATH
                from basic_pitch.inference import Model

                from app.services.audio.transcription.inference import (
                    MODEL_VERSION,
                    runtime_name,
                    runtime_version,
                )

                self._model = Model(ICASSP_2022_MODEL_PATH)
                self._state.load_seconds = round(time.perf_counter() - started, 3)
                self._state.loaded_at = time.time()
                self._state.model_version = MODEL_VERSION
                self._state.runtime = f"{runtime_name()} {runtime_version() or ''}".strip()
                self._state.status = "ready"
                logger.info(
                    "basic pitch model loaded in %.3fs (runtime=%s)",
                    self._state.load_seconds,
                    self._state.runtime,
                )
            except Exception as exc:  # pragma: no cover - depends on install
                self._state.status = "failed"
                self._state.error = f"{type(exc).__name__}: {exc}"
                self._state.load_seconds = round(time.perf_counter() - started, 3)
                logger.error("basic pitch model failed to load: %s", self._state.error)
                return self._state

        if warmup:
            self.warmup()
        return self._state

    def warmup(self) -> Optional[float]:
        """Run one throwaway inference so the first real job is not slow.

        The cost is dominated by librosa/numba JIT (~3.7 s) plus ORT graph
        warm-up, so doing it at boot keeps the first user request fast.
        """
        if self._state.status != "ready" or self._model is None:
            return None
        started = time.perf_counter()
        try:
            import tempfile
            import wave
            from pathlib import Path

            from basic_pitch.inference import predict

            with tempfile.TemporaryDirectory(prefix="pocketscore-warmup-") as tmp:
                path = Path(tmp) / "warmup.wav"
                with wave.open(str(path), "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(22050)
                    handle.writeframes(b"\x00\x00" * 22050)  # 1 s of silence
                predict(str(path), self._model)
            self._state.warmup_seconds = round(time.perf_counter() - started, 3)
            logger.info("basic pitch warm-up finished in %.3fs", self._state.warmup_seconds)
        except Exception as exc:  # pragma: no cover - defensive
            # A warm-up failure is not fatal: the model itself loaded fine.
            self._state.extra["warmup_error"] = f"{type(exc).__name__}: {exc}"
            logger.warning("basic pitch warm-up failed: %s", self._state.extra["warmup_error"])
        return self._state.warmup_seconds

    # -- access ------------------------------------------------------------
    def get(self) -> Any:
        """Return the model instance, loading it on first use."""
        if self._state.status != "ready":
            self.load()
        if self._state.status != "ready":
            raise RuntimeError(self._state.error or "model_unavailable")
        return self._model

    @property
    def state(self) -> ModelState:
        return self._state

    @property
    def is_ready(self) -> bool:
        return self._state.status == "ready"

    def status(self) -> Dict[str, Any]:
        return self._state.as_dict()

    def mark_call(self) -> int:
        with self._lock:
            self._inference_calls += 1
            return self._inference_calls

    @property
    def inference_calls(self) -> int:
        return self._inference_calls

    # -- test helpers ------------------------------------------------------
    def reset(self) -> None:
        """Drop the cached model (tests only)."""
        with self._lock:
            self._model = None
            self._state = ModelState()
            self._inference_calls = 0


model_manager = ModelManager()
