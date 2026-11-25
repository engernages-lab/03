"""Configurable post-processing for audio transcription (V1.1-A).

The pipeline is deliberately split into named stages so each strategy can be
tuned and regression-tested on its own:

    model_inference -> onset_detection -> harmonic_analysis -> note_filtering
    -> note_splitting -> note_merging -> confidence_calibration -> conversion

Every stage keeps the raw model output intact: :class:`TranscriptionResult`
carries both ``raw`` and ``notes`` so a caller (or the UI) can compare the
model's first opinion with what was finally written to the document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DetectedNote:
    """One note in seconds, as produced by the model (or a stage)."""

    pitch: int
    start: float
    end: float
    amplitude: float = 1.0
    confidence: Optional[float] = None
    source: str = "model"

    @property
    def duration(self) -> float:
        return max(self.end - self.start, 1e-3)


@dataclass
class TranscriptionConfig:
    """All tunables. Defaults are the V1.1-A tuned values."""

    # -- model inference ---------------------------------------------------
    onset_threshold: float = 0.5
    frame_threshold: float = 0.3
    minimum_note_length_ms: float = 58.0
    minimum_frequency: Optional[float] = None
    maximum_frequency: Optional[float] = None
    max_notes: int = 5_000
    melodia_trick: bool = True

    # -- repeated-note splitting ------------------------------------------
    split_on_onsets: bool = True
    # energy dip (relative to the note's own peak) that marks a re-attack
    split_energy_dip: float = 0.45
    # ...and it must also sit this far below the note's median energy, so a flat
    # sustained note (whose noisy RMS has many technical minima) is never split
    split_energy_median_ratio: float = 0.55
    onset_delta: float = 0.07
    onset_wait: float = 0
    split_min_segment: float = 0.07
    # a fragment shorter than this next to a same-pitch note is an artefact
    merge_sliver: float = 0.10
    split_max_segments: int = 8

    # -- harmonic (octave / fifth) false-positive suppression --------------
    suppress_harmonics: bool = True
    # intervals (semitones) that a real played note can also excite as an overtone
    harmonic_intervals: tuple = (12, 19, 24, 28, 31, 34, 36, 38, 40, 43, 48)
    harmonic_onset_tolerance: float = 0.07
    # the upper note must be clearly weaker than its candidate fundamental
    harmonic_amplitude_ratio: float = 0.78
    # and must not outlast it (a real octave chord usually holds as long)
    harmonic_duration_ratio: float = 1.25
    harmonic_overlap: float = 0.5
    # a weak upper note fully contained inside a sounding fundamental is an
    # overtone even when it starts late (model reports overtones after the attack)
    harmonic_contained: bool = True
    harmonic_contained_ratio: float = 0.6

    # -- filtering ---------------------------------------------------------
    min_duration: float = 0.05
    min_pitch: int = 21
    max_pitch: int = 108
    min_amplitude: float = 0.05

    # -- merging -----------------------------------------------------------
    merge_gap: float = 0.06
    merge_same_pitch_only: bool = True

    # -- confidence calibration -------------------------------------------
    # amplitude is a model score, not a probability; it is mapped through this
    # curve and capped so the UI never claims certainty it cannot back up.
    confidence_gain: float = 0.85
    confidence_cap: float = 0.95

    def as_dict(self) -> dict:
        return {
            "onset_threshold": self.onset_threshold,
            "frame_threshold": self.frame_threshold,
            "minimum_note_length_ms": self.minimum_note_length_ms,
            "melodia_trick": self.melodia_trick,
            "split_on_onsets": self.split_on_onsets,
            "split_min_segment": self.split_min_segment,
            "suppress_harmonics": self.suppress_harmonics,
            "harmonic_amplitude_ratio": self.harmonic_amplitude_ratio,
            "harmonic_duration_ratio": self.harmonic_duration_ratio,
            "min_duration": self.min_duration,
            "merge_gap": self.merge_gap,
        }


@dataclass
class TranscriptionResult:
    notes: List[DetectedNote]
    raw: List[DetectedNote]
    config: TranscriptionConfig
    onsets: List[float] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def removed_as_harmonic(self) -> int:
        return int(self.stats.get("removed_harmonic", 0))

    @property
    def added_by_split(self) -> int:
        return int(self.stats.get("split_extra", 0))
