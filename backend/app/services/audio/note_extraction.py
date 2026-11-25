"""Audio -> note events facade.

The implementation lives in :mod:`app.services.audio.transcription` (V1.1-A
split the pipeline into inference + named post-processing stages). This module
keeps the public names the rest of the app and the tests already use.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from app.services.audio.transcription import (  # noqa: F401
    MODEL_ID,
    MODEL_LICENSE,
    MODEL_NAME,
    MODEL_SOURCE,
    MODEL_VERSION,
    DetectedNote,
    TranscriptionConfig,
    TranscriptionResult,
    model_status,
    run_model,
)
from app.services.audio.transcription import transcribe as _transcribe
from app.services.audio.transcription.conversion import (  # noqa: F401
    QUANTISE_BEATS,
    build_document,
)

# Basic Pitch works at ~11 kHz internally and is trained on 22050 Hz audio.
EXPECTED_SAMPLE_RATE = 22_050


def transcribe_result(
    path: Path, config: Optional[TranscriptionConfig] = None
) -> TranscriptionResult:
    """Full result including the untouched model output for comparison."""
    return _transcribe(Path(path), config)


def transcribe_file(
    path: Path,
    *,
    onset_threshold: float = 0.5,
    frame_threshold: float = 0.3,
    minimum_note_length_ms: float = 58.0,
    minimum_frequency: Optional[float] = None,
    maximum_frequency: Optional[float] = None,
    max_notes: int = 5_000,
    config: Optional[TranscriptionConfig] = None,
) -> List[DetectedNote]:
    """Run the model and return post-processed note events (seconds, MIDI pitch).

    Raises ``RuntimeError`` when the model is unavailable so callers can map it
    to ``REQUIRES_MODEL`` instead of silently producing an empty result.
    """
    active = config or TranscriptionConfig(
        onset_threshold=onset_threshold,
        frame_threshold=frame_threshold,
        minimum_note_length_ms=minimum_note_length_ms,
        minimum_frequency=minimum_frequency,
        maximum_frequency=maximum_frequency,
        max_notes=max_notes,
    )
    return _transcribe(Path(path), active).notes


__all__ = [
    "MODEL_ID",
    "MODEL_NAME",
    "MODEL_VERSION",
    "MODEL_LICENSE",
    "MODEL_SOURCE",
    "EXPECTED_SAMPLE_RATE",
    "QUANTISE_BEATS",
    "DetectedNote",
    "TranscriptionConfig",
    "TranscriptionResult",
    "model_status",
    "run_model",
    "transcribe_result",
    "transcribe_file",
    "build_document",
]
