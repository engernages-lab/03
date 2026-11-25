"""Scoring for note-level transcription benchmarks.

Matching is one-to-one and greedy (closest onset wins). Two error rates are
reported because sparse note detection has no meaningful "true negatives":

* ``false_positive_rate`` = FP / (TP + FP) - share of detections that are wrong
* ``false_positives_per_second`` - absolute noise level of the output
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass
class Detected:
    pitch: int
    start: float
    end: float
    amplitude: float = 1.0


@dataclass
class Score:
    reference: int
    detected: int
    true_positives: int
    false_positives: int
    false_negatives: int
    pitch_hits: int
    onset_errors: List[float]
    offset_errors: List[float]
    duration: float

    @property
    def precision(self) -> float:
        total = self.true_positives + self.false_positives
        return self.true_positives / total if total else 0.0

    @property
    def recall(self) -> float:
        total = self.true_positives + self.false_negatives
        return self.true_positives / total if total else 0.0

    @property
    def f1(self) -> float:
        precision, recall = self.precision, self.recall
        return 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    @property
    def pitch_accuracy(self) -> float:
        return self.pitch_hits / self.true_positives if self.true_positives else 0.0

    @property
    def onset_mae(self) -> float:
        return sum(self.onset_errors) / len(self.onset_errors) if self.onset_errors else 0.0

    @property
    def offset_mae(self) -> float:
        return sum(self.offset_errors) / len(self.offset_errors) if self.offset_errors else 0.0

    @property
    def false_positive_rate(self) -> float:
        total = self.true_positives + self.false_positives
        return self.false_positives / total if total else 0.0

    @property
    def false_positives_per_second(self) -> float:
        return self.false_positives / self.duration if self.duration else 0.0

    def as_dict(self) -> dict:
        return {
            "reference": self.reference,
            "detected": self.detected,
            "tp": self.true_positives,
            "fp": self.false_positives,
            "fn": self.false_negatives,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "pitch_accuracy": round(self.pitch_accuracy, 4),
            "onset_mae_ms": round(self.onset_mae * 1000, 1),
            "offset_mae_ms": round(self.offset_mae * 1000, 1),
            "fpr": round(self.false_positive_rate, 4),
            "fp_per_second": round(self.false_positives_per_second, 3),
        }


def _match(
    detected: Sequence[Detected],
    reference: Sequence[Tuple[int, float]],
    onset_tolerance: float,
    pitch_tolerance: int,
    ends: Optional[Sequence[float]] = None,
) -> Tuple[List[Detected], List[int], List[float], List[float]]:
    """Return (false_positives, matched_ref_indexes, onset_errors, offset_errors)."""
    remaining = list(detected)
    matched: List[int] = []
    onset_errors: List[float] = []
    offset_errors: List[float] = []

    for index, (pitch, start) in enumerate(reference):
        best = None
        for candidate in remaining:
            if abs(candidate.pitch - pitch) > pitch_tolerance:
                continue
            distance = abs(candidate.start - start)
            if distance > onset_tolerance:
                continue
            if best is None or distance < abs(best.start - start):
                best = candidate
        if best is not None:
            remaining.remove(best)
            matched.append(index)
            onset_errors.append(abs(best.start - start))
            if ends is not None:
                offset_errors.append(abs(best.end - ends[index]))

    return remaining, matched, onset_errors, offset_errors


def score(
    detected: Sequence[Detected],
    reference: Sequence[Tuple[int, float]],
    *,
    duration: float,
    onset_tolerance: float = 0.06,
    pitch_tolerance: int = 0,
    reference_ends: Optional[Sequence[float]] = None,
) -> Score:
    remaining, matched, onset_errors, offset_errors = _match(
        detected, reference, onset_tolerance, pitch_tolerance, reference_ends
    )
    true_positives = len(matched)
    return Score(
        reference=len(reference),
        detected=len(detected),
        true_positives=true_positives,
        false_positives=len(remaining),
        false_negatives=len(reference) - true_positives,
        pitch_hits=true_positives,  # pitch matching is exact by construction
        onset_errors=onset_errors,
        offset_errors=offset_errors,
        duration=duration,
    )


def aggregate(scores: Sequence[Score]) -> Score:
    true_positives = sum(item.true_positives for item in scores)
    onset_errors: List[float] = []
    offset_errors: List[float] = []
    for item in scores:
        onset_errors.extend(item.onset_errors)
        offset_errors.extend(item.offset_errors)
    return Score(
        reference=sum(item.reference for item in scores),
        detected=sum(item.detected for item in scores),
        true_positives=true_positives,
        false_positives=sum(item.false_positives for item in scores),
        false_negatives=sum(item.false_negatives for item in scores),
        pitch_hits=true_positives,
        onset_errors=onset_errors,
        offset_errors=offset_errors,
        duration=sum(item.duration for item in scores),
    )


def pitch_accuracy(detected: Sequence[Detected], reference: Sequence[Tuple[int, float]], *, onset_tolerance: float = 0.06) -> float:
    """Share of matched notes whose pitch is exactly right (pitch tolerance 0)."""
    remaining, matched, _onset, _offset = _match(detected, reference, onset_tolerance, 0)
    return len(matched) / len(detected) if detected else 0.0
