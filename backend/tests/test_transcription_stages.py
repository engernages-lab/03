"""Unit tests for the V1.1-A post-processing stages.

These run without audio: every stage takes note lists and returns note lists, so
the strategies can be pinned down deterministically.
"""

from __future__ import annotations

import pytest

from app.services.audio.transcription import stages
from app.services.audio.transcription.config import DetectedNote, TranscriptionConfig


def note(pitch: int, start: float, end: float, amplitude: float = 0.8, source: str = "model") -> DetectedNote:
    return DetectedNote(pitch=pitch, start=start, end=end, amplitude=amplitude, source=source)


def test_harmonic_suppression_removes_weak_octave_overtones():
    config = TranscriptionConfig()
    notes = [
        note(60, 0.0, 0.8, 0.85),  # fundamental
        note(72, 0.0, 0.8, 0.35),  # weak octave -> overtone
        note(84, 0.02, 0.7, 0.2),  # weaker double octave -> overtone
    ]
    kept, removed = stages.suppress_harmonics(notes, config)
    assert [item.pitch for item in kept] == [60]
    assert removed == 2


def test_harmonic_suppression_keeps_real_octave_chord():
    """A genuinely played octave has comparable amplitude and length."""
    config = TranscriptionConfig()
    notes = [note(48, 0.0, 0.8, 0.85), note(60, 0.0, 0.8, 0.82)]
    kept, removed = stages.suppress_harmonics(notes, config)
    assert sorted(item.pitch for item in kept) == [48, 60]
    assert removed == 0


def test_harmonic_suppression_keeps_real_fifth():
    config = TranscriptionConfig()
    notes = [note(48, 0.0, 0.8, 0.8), note(55, 0.0, 0.8, 0.78)]
    kept, removed = stages.suppress_harmonics(notes, config)
    assert sorted(item.pitch for item in kept) == [48, 55]
    assert removed == 0


def test_harmonic_suppression_keeps_unrelated_interval():
    config = TranscriptionConfig()
    notes = [note(60, 0.0, 0.8, 0.9), note(63, 0.0, 0.8, 0.4)]  # minor third, quiet
    kept, removed = stages.suppress_harmonics(notes, config)
    assert sorted(item.pitch for item in kept) == [60, 63]
    assert removed == 0


def test_harmonic_suppression_detects_late_contained_overtone():
    """The model sometimes reports an overtone after the fundamental attack."""
    config = TranscriptionConfig()
    notes = [note(79, 0.7, 1.34, 0.78), note(91, 1.1, 1.22, 0.32)]
    kept, removed = stages.suppress_harmonics(notes, config)
    assert [item.pitch for item in kept] == [79]
    assert removed == 1


def test_harmonic_suppression_finds_fundamental_reported_later():
    """Clustering by onset means ordering in the input does not matter."""
    config = TranscriptionConfig()
    notes = [note(72, 0.0, 0.8, 0.3), note(60, 0.01, 0.8, 0.85)]
    kept, removed = stages.suppress_harmonics(notes, config)
    assert [item.pitch for item in kept] == [60]
    assert removed == 1


def test_harmonic_suppression_can_be_disabled():
    config = TranscriptionConfig(suppress_harmonics=False)
    notes = [note(60, 0.0, 0.8, 0.85), note(72, 0.0, 0.8, 0.3)]
    kept, removed = stages.suppress_harmonics(notes, config)
    assert len(kept) == 2 and removed == 0


def test_filter_drops_short_low_amplitude_and_out_of_range_notes():
    config = TranscriptionConfig()
    notes = [
        note(60, 0.0, 0.02),  # too short
        note(60, 0.1, 0.5, 0.01),  # too quiet
        note(10, 0.1, 0.5),  # below the piano range
        note(60, 0.2, 0.6),  # fine
    ]
    kept, dropped = stages.filter_notes(notes, config)
    assert [item.pitch for item in kept] == [60]
    assert dropped == 3


def test_merge_joins_model_reattack_without_energy_evidence():
    config = TranscriptionConfig()
    notes = [note(60, 0.0, 0.30), note(60, 0.32, 0.60)]
    merged = stages.merge_adjacent(notes, config)
    assert len(merged) == 1
    assert merged[0].start == pytest.approx(0.0)
    assert merged[0].end == pytest.approx(0.60)


def test_merge_keeps_split_segments_apart():
    config = TranscriptionConfig()
    notes = [
        DetectedNote(pitch=60, start=0.0, end=0.2, amplitude=0.8, source="model+energy-split"),
        DetectedNote(pitch=60, start=0.2, end=0.4, amplitude=0.8, source="model+energy-split"),
    ]
    merged = stages.merge_adjacent(notes, config)
    assert len(merged) == 2


def test_merge_joins_sliver_fragments():
    config = TranscriptionConfig()
    notes = [note(60, 0.0, 0.30), note(60, 0.31, 0.39)]  # 80 ms tail
    merged = stages.merge_adjacent(notes, config, envelope=(_times(), _rms()))
    assert len(merged) == 1


def test_merge_respects_a_real_reattack():
    """With energy evidence of a re-attack the two notes stay separate."""
    config = TranscriptionConfig()
    notes = [note(60, 0.0, 0.15), note(60, 0.15, 0.30)]
    merged = stages.merge_adjacent(notes, config, envelope=_reattack_envelope())
    assert len(merged) == 2


def test_confidence_is_capped_and_never_claims_certainty():
    config = TranscriptionConfig()
    notes = [note(60, 0.0, 0.5, 1.0), note(64, 0.6, 0.9, 0.2)]
    calibrated = stages.calibrate_confidence(notes, config)
    assert all(item.confidence is not None for item in calibrated)
    assert max(item.confidence for item in calibrated) <= config.confidence_cap
    assert calibrated[0].confidence > calibrated[1].confidence


def test_quality_summary_reports_low_confidence_and_polyphony():
    config = TranscriptionConfig()
    notes = [
        DetectedNote(pitch=60, start=0.0, end=0.4, amplitude=0.9, confidence=0.8),
        DetectedNote(pitch=64, start=0.0, end=0.4, amplitude=0.9, confidence=0.8),
        DetectedNote(pitch=67, start=0.5, end=0.9, amplitude=0.3, confidence=0.2),
    ]
    summary = stages.quality_summary(notes, config)
    assert summary["notes"] == 3
    assert summary["low_confidence"] == 1
    assert summary["low_confidence_ratio"] == pytest.approx(1 / 3, abs=1e-3)
    assert summary["polyphonic_share"] > 0.5  # two notes share the first onset
    assert "复音" in summary["review_hint"]


def test_quality_summary_handles_empty_result():
    summary = stages.quality_summary([], TranscriptionConfig())
    assert summary["notes"] == 0
    assert summary["review_hint"] == "未检测到音符"


# -- tiny synthetic envelopes ------------------------------------------------


def _times():
    import numpy as np

    return np.linspace(0.0, 0.6, 61)


def _rms():
    import numpy as np

    return np.full(61, 0.5)


def _reattack_envelope():
    """Flat, then a deep dip, then a rise - a real re-attack."""
    import numpy as np

    times = np.linspace(0.0, 0.4, 41)
    values = np.full(41, 0.5)
    values[18:22] = 0.05
    return times, values
