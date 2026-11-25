"""Pipeline orchestration for audio transcription (V1.1-A)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from app.services.audio.transcription import stages
from app.services.audio.transcription.config import (
    DetectedNote,
    TranscriptionConfig,
    TranscriptionResult,
)
from app.services.audio.transcription.inference import run_model


def transcribe(
    path: Path, config: Optional[TranscriptionConfig] = None
) -> TranscriptionResult:
    """Run inference + every post-processing stage, keeping the raw output."""
    active = config or TranscriptionConfig()
    raw = run_model(path, active)

    onsets = stages.detect_onsets(path, active) if active.split_on_onsets else []
    envelope = stages.energy_envelope(path) if active.split_on_onsets else (None, None)

    working: List[DetectedNote] = list(raw)
    stats: dict = {"raw": len(raw), "onsets": len(onsets)}

    working, removed_harmonic = stages.suppress_harmonics(working, active)
    stats["removed_harmonic"] = removed_harmonic

    working, dropped = stages.filter_notes(working, active)
    stats["filtered"] = dropped

    working, split_extra = stages.split_by_energy(working, path, active, envelope=envelope)
    stats["split_extra"] = split_extra

    working = stages.merge_adjacent(working, active, envelope=envelope)
    stats["merged"] = len(working)

    working = stages.calibrate_confidence(working, active)
    working.sort(key=lambda note: (note.start, note.pitch))

    stats["final"] = len(working)
    stats["quality"] = stages.quality_summary(working, active)

    return TranscriptionResult(
        notes=working,
        raw=raw,
        config=active,
        onsets=onsets,
        stats=stats,
    )
