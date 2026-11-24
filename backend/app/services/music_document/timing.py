"""Beat <-> time conversions and measure/beat location.

This is the **only** place where time-signature arithmetic happens.  Grid
notation, jianpu notation, the MIDI importer and the API all call into here.
"""

from __future__ import annotations

import math

from app.schemas.music_document import EPSILON, TimeSignature


def beats_per_measure(time_signature: TimeSignature) -> float:
    return time_signature.numerator * 4.0 / time_signature.denominator


def beats_to_seconds(beats: float, tempo: float) -> float:
    if tempo <= 0:
        raise ValueError("tempo must be positive")
    return beats * 60.0 / tempo


def seconds_to_beats(seconds: float, tempo: float) -> float:
    if tempo <= 0:
        raise ValueError("tempo must be positive")
    return seconds * tempo / 60.0


def locate_beat(position: float, time_signature: TimeSignature) -> tuple[int, float]:
    """Return ``(measure, beat)`` for an absolute beat position.

    ``measure`` is 1-based and ``beat`` is 1-based within the measure, e.g. a
    note at beat 5 in 4/4 is ``(2, 2.0)``.
    """
    if position < 0:
        raise ValueError("position must be non-negative")
    measure_length = beats_per_measure(time_signature)
    if measure_length <= 0:
        return 1, 1.0
    # nudge values that sit exactly on a boundary to avoid 0.999999 -> measure 1
    adjusted = position + EPSILON
    measure_index = int(adjusted // measure_length)
    offset = position - measure_index * measure_length
    if offset < 0:
        offset = 0.0
    return measure_index + 1, round(offset + 1.0, 6)


def measure_start(measure: int, time_signature: TimeSignature) -> float:
    """Absolute beat at which ``measure`` (1-based) begins."""
    if measure < 1:
        raise ValueError("measure must be >= 1")
    return (measure - 1) * beats_per_measure(time_signature)


def quantize(value: float, divisions: int) -> float:
    """Snap a beat value to the nearest ``1/divisions`` grid point."""
    if divisions <= 0:
        raise ValueError("divisions must be positive")
    step = 1.0 / divisions
    return round(round(value / step) * step, 6)


def slot_index(position: float, measure: int, divisions: int, time_signature: TimeSignature) -> int:
    """Grid slot of ``position`` inside ``measure``."""
    start = measure_start(measure, time_signature)
    return int(round((position - start) * divisions))


def duration_in_slots(duration: float, divisions: int) -> int:
    return max(1, int(round(duration * divisions)))


def format_beat(value: float) -> str:
    """Human readable beat, e.g. ``3.5`` -> ``3.5``, ``4.0`` -> ``4``."""
    if abs(value - round(value)) < EPSILON:
        return str(int(round(value)))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def ceil_measures(total_beats: float, time_signature: TimeSignature) -> int:
    bpm = beats_per_measure(time_signature)
    if bpm <= 0:
        return 1
    return max(1, math.ceil((total_beats - EPSILON) / bpm))
