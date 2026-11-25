"""Post-processing stages for audio transcription.

Each function is pure (takes notes, returns notes) so it can be unit-tested
without audio and composed in any order.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence

from app.services.audio.transcription.config import DetectedNote, TranscriptionConfig


def detect_onsets(path, config: TranscriptionConfig) -> List[float]:
    """Onset times (seconds) from librosa's onset strength envelope."""
    try:
        import librosa
    except Exception:  # pragma: no cover - librosa is a runtime dependency
        return []
    try:
        samples, sample_rate = librosa.load(str(path), sr=22050, mono=True)
        frames = librosa.onset.onset_detect(
            y=samples,
            sr=sample_rate,
            backtrack=True,
            units="time",
            delta=config.onset_delta,
            wait=config.onset_wait,
        )
        return sorted(float(value) for value in frames)
    except Exception:  # pragma: no cover - defensive
        return []


def energy_envelope(
    path, *, sample_rate: int = 22050, hop: int = 256, frame: int = 1024
) -> tuple:
    """Short-term RMS curve of the audio, used as evidence for split/merge."""
    try:
        import librosa
    except Exception:  # pragma: no cover - optional
        return None, None
    try:
        samples, sr = librosa.load(str(path), sr=sample_rate, mono=True)
    except Exception:  # pragma: no cover - defensive
        return None, None
    if samples.size == 0:
        return None, None
    rms = librosa.feature.rms(y=samples, frame_length=frame, hop_length=hop)[0]
    times = librosa.frames_to_time(range(len(rms)), sr=sr, hop_length=hop)
    return times, rms


def _window(times, rms, start: float, end: float):
    mask = (times >= start) & (times <= end)
    return times[mask], rms[mask]


def has_reattack(times, rms, start: float, end: float, config: TranscriptionConfig) -> bool:
    """True when the energy between ``start`` and ``end`` dips and rises again."""
    if times is None or rms is None or end <= start:
        return False
    positions, values = _window(times, rms, start, end)
    if len(values) < 4:
        return False
    peak = float(values.max())
    if peak <= 1e-6:
        return False
    median = float(sorted(values)[len(values) // 2])
    threshold = min(peak * config.split_energy_dip, median * config.split_energy_median_ratio)
    for index in range(1, len(values) - 1):
        value = values[index]
        if value >= threshold:
            continue
        if value <= values[index - 1] and value <= values[index + 1] and values[index + 1] > value * 1.15:
            return True
    return False


def _overlap(a: DetectedNote, b: DetectedNote) -> float:
    return max(0.0, min(a.end, b.end) - max(a.start, b.start))


def suppress_harmonics(
    notes: Sequence[DetectedNote], config: TranscriptionConfig
) -> tuple[List[DetectedNote], int]:
    """Drop upper notes that are almost certainly overtones of a lower note.

    A note is removed only when *all* of these hold, so genuine octave or fifth
    chords survive:

    * the interval is a known overtone interval (octave / twelfth / double octave …)
    * the onsets coincide (an overtone starts with its fundamental)
    * they overlap substantially
    * the upper note is clearly weaker (``harmonic_amplitude_ratio``)
    * the upper note does not outlast the candidate fundamental

    Notes are grouped by onset first and processed low-to-high, so a fundamental
    that the model reports *after* its overtone is still found.
    """
    if not config.suppress_harmonics or not notes:
        return list(notes), 0

    ordered = sorted(notes, key=lambda item: (round(item.start / 0.02), item.pitch))
    clusters: List[List[DetectedNote]] = []
    for note in ordered:
        if clusters and abs(note.start - clusters[-1][0].start) <= config.harmonic_onset_tolerance:
            clusters[-1].append(note)
        else:
            clusters.append([note])

    kept: List[DetectedNote] = []
    removed = 0
    for cluster in clusters:
        survivors: List[DetectedNote] = []
        for note in sorted(cluster, key=lambda item: item.pitch):
            parent = None
            for candidate in survivors:
                interval = note.pitch - candidate.pitch
                if interval not in config.harmonic_intervals:
                    continue
                if abs(note.start - candidate.start) > config.harmonic_onset_tolerance:
                    continue
                if _overlap(note, candidate) < config.harmonic_overlap * min(
                    note.duration, candidate.duration
                ):
                    continue
                if note.amplitude >= config.harmonic_amplitude_ratio * candidate.amplitude:
                    continue
                if note.duration > config.harmonic_duration_ratio * candidate.duration:
                    continue
                parent = candidate
                break
            if parent is not None:
                removed += 1
                continue
            survivors.append(note)
        kept.extend(survivors)

    # second pass: an upper note that starts late but sits entirely inside a
    # louder fundamental's span is still an overtone of it
    if config.harmonic_contained:
        remaining: List[DetectedNote] = []
        for note in kept:
            container = None
            for candidate in kept:
                if candidate is note or candidate.pitch >= note.pitch:
                    continue
                if (note.pitch - candidate.pitch) not in config.harmonic_intervals:
                    continue
                if note.start < candidate.start - 0.02 or note.end > candidate.end + 0.02:
                    continue
                if note.amplitude >= config.harmonic_amplitude_ratio * candidate.amplitude:
                    continue
                if note.duration > config.harmonic_contained_ratio * candidate.duration:
                    continue
                container = candidate
                break
            if container is not None:
                removed += 1
                continue
            remaining.append(note)
        kept = remaining

    kept.sort(key=lambda note: (note.start, note.pitch))
    return kept, removed


def filter_notes(
    notes: Sequence[DetectedNote], config: TranscriptionConfig
) -> tuple[List[DetectedNote], int]:
    """Remove notes outside the musical/robustness envelope."""
    kept: List[DetectedNote] = []
    dropped = 0
    for note in notes:
        if note.duration < config.min_duration:
            dropped += 1
            continue
        if not (config.min_pitch <= note.pitch <= config.max_pitch):
            dropped += 1
            continue
        if note.amplitude < config.min_amplitude:
            dropped += 1
            continue
        kept.append(note)
    return kept, dropped


def split_on_onsets(
    notes: Sequence[DetectedNote], onsets: Sequence[float], config: TranscriptionConfig
) -> tuple[List[DetectedNote], int]:
    """Split a note at onset times that fall inside it (legacy path)."""
    if not config.split_on_onsets or not onsets:
        return list(notes), 0

    output: List[DetectedNote] = []
    added = 0
    for note in notes:
        inside = [
            time
            for time in onsets
            if note.start + config.split_min_segment < time < note.end - config.split_min_segment
        ]
        boundaries = [note.start]
        for time in inside:
            if time - boundaries[-1] >= config.split_min_segment and note.end - time >= config.split_min_segment:
                boundaries.append(time)
        if len(boundaries) == 1 or len(boundaries) > config.split_max_segments:
            output.append(note)
            continue
        boundaries.append(note.end)
        for index in range(len(boundaries) - 1):
            output.append(
                DetectedNote(
                    pitch=note.pitch,
                    start=boundaries[index],
                    end=boundaries[index + 1],
                    amplitude=note.amplitude,
                    confidence=note.confidence,
                    source=f"{note.source}+split",
                )
            )
        added += len(boundaries) - 2
    return output, added


def split_by_energy(
    notes: Sequence[DetectedNote],
    path,
    config: TranscriptionConfig,
    *,
    envelope: tuple | None = None,
    sample_rate: int = 22050,
    hop: int = 256,
) -> tuple[List[DetectedNote], int]:
    """Split repeated notes where the energy envelope drops and rises again.

    Basic Pitch normally merges a repeated pitch into one event. A real re-attack
    shows a dip in the short-term RMS followed by a rise; a sustained or decaying
    note does not. Splitting there is evidence-based, not a guess.
    """
    if not config.split_on_onsets or not notes:
        return list(notes), 0
    try:
        import librosa  # noqa: F401
    except Exception:  # pragma: no cover - optional
        return list(notes), 0

    times, rms = envelope if envelope else energy_envelope(path, sample_rate=sample_rate, hop=hop)
    if times is None or rms is None or len(rms) == 0:
        return list(notes), 0

    output: List[DetectedNote] = []
    added = 0
    other_starts = [note.start for note in notes]
    for note in notes:
        window = (times >= note.start) & (times <= note.end)
        if window.sum() < 6:
            output.append(note)
            continue
        values = rms[window]
        positions = times[window]
        local_max = float(values.max())
        if local_max <= 1e-6:
            output.append(note)
            continue

        # a split point is a local minimum well below the note's own peak and
        # its median energy whose successor rises again - the signature of a
        # re-attack (a flat sustained note has none of the second condition)
        boundaries = [note.start]
        median = float(sorted(values)[len(values) // 2])
        threshold = min(local_max * config.split_energy_dip, median * config.split_energy_median_ratio)
        for index in range(1, len(values) - 1):
            value = values[index]
            if value >= threshold:
                continue
            if not (value <= values[index - 1] and value <= values[index + 1]):
                continue
            if values[index + 1] < values[index] * 1.15:
                continue
            time = float(positions[index + 1])
            if time - boundaries[-1] < config.split_min_segment:
                continue
            if note.end - time < config.split_min_segment:
                continue
            # an energy dip caused by another pitch entering is polyphony, not a
            # re-attack of this note
            if any(
                abs(other - time) <= 0.06 and abs(other - note.start) > 1e-6
                for other in other_starts
            ):
                continue
            boundaries.append(time)

        if len(boundaries) == 1 or len(boundaries) > config.split_max_segments:
            output.append(note)
            continue
        boundaries.append(note.end)
        for index in range(len(boundaries) - 1):
            output.append(
                DetectedNote(
                    pitch=note.pitch,
                    start=boundaries[index],
                    end=boundaries[index + 1],
                    amplitude=note.amplitude,
                    confidence=note.confidence,
                    source=f"{note.source}+energy-split",
                )
            )
        added += len(boundaries) - 2
    return output, added


def merge_adjacent(
    notes: Iterable[DetectedNote],
    config: TranscriptionConfig,
    envelope: tuple | None = None,
) -> List[DetectedNote]:
    """Join same-pitch segments the model split at a dip in a *sustained* note.

    Merging is evidence-gated: two abutting same-pitch segments are joined only
    when the energy between them shows **no** re-attack. Genuinely repeated notes
    have a valley there, so they stay separate (that is TD-02's fix).
    """
    times, rms = envelope if envelope else (None, None)
    ordered = sorted(notes, key=lambda item: (item.start, item.pitch))
    merged: List[DetectedNote] = []
    for note in ordered:
        # the segment to join is the most recent one *of this pitch*, not simply
        # the previous entry: in polyphony another voice can start in between
        previous = None
        for candidate in reversed(merged):
            if candidate.pitch == note.pitch:
                previous = candidate
                break
            if note.start - candidate.end > config.merge_gap:
                break
        joinable = (
            previous is not None
            and note.start - previous.end <= config.merge_gap
            and note.start - previous.start > 1e-9
            and "split" not in previous.source
            and "split" not in note.source
        )
        if joinable and times is not None:
            # An energy dip at the junction only proves a re-attack of *this*
            # pitch. If another pitch starts there, the dip belongs to that
            # voice (polyphony), so the held note is a continuation.
            polyphonic = any(
                other is not note
                and other.pitch != note.pitch
                and abs(other.start - note.start) <= 0.06
                for other in ordered
            )
            if not polyphonic:
                left = max(previous.start, note.start - 0.12)
                right = min(note.end, note.start + 0.12)
                if has_reattack(times, rms, left, right, config):
                    # a sliver shorter than the split minimum is a model
                    # artefact, not a real repeat
                    sliver = min(previous.duration, note.duration) < config.merge_sliver
                    if not sliver:
                        joinable = False
        if joinable:
            previous.end = max(previous.end, note.end)
            previous.amplitude = max(previous.amplitude, note.amplitude)
        else:
            merged.append(note)
    return merged


def calibrate_confidence(
    notes: Sequence[DetectedNote], config: TranscriptionConfig
) -> List[DetectedNote]:
    """Map the model amplitude to a bounded confidence score.

    The amplitude is a *detection strength*, not a calibrated probability, so it
    is scaled by ``confidence_gain`` and capped at ``confidence_cap``; the UI
    must describe it as a heuristic hint, never as accuracy.
    """
    output: List[DetectedNote] = []
    for note in notes:
        value = min(config.confidence_cap, max(0.0, note.amplitude * config.confidence_gain))
        output.append(
            DetectedNote(
                pitch=note.pitch,
                start=note.start,
                end=note.end,
                amplitude=note.amplitude,
                confidence=round(value, 4),
                source=note.source,
            )
        )
    return output


def quality_summary(notes: Sequence[DetectedNote], config: TranscriptionConfig) -> dict:
    """Aggregate stats shown to the user (never presented as accuracy)."""
    if not notes:
        return {
            "notes": 0,
            "mean_confidence": 0.0,
            "low_confidence": 0,
            "low_confidence_ratio": 0.0,
            "polyphonic_share": 0.0,
            "review_hint": "未检测到音符",
        }
    confidences = [note.confidence or 0.0 for note in notes]
    low = [value for value in confidences if value < 0.55]
    starts = sorted(note.start for note in notes)
    simultaneous = 0
    for start in starts:
        group = [other for other in starts if abs(other - start) < 0.05]
        if len(group) > 1:
            simultaneous += 1
    return {
        "notes": len(notes),
        "mean_confidence": round(sum(confidences) / len(confidences), 4),
        "low_confidence": len(low),
        "low_confidence_ratio": round(len(low) / len(notes), 4),
        "polyphonic_share": round(simultaneous / len(notes), 4),
        "review_hint": (
            "存在同时发声，复音结果建议逐和弦校对"
            if simultaneous / len(notes) > 0.15
            else "单声部为主，仍建议抽查低置信度音符"
        ),
    }
