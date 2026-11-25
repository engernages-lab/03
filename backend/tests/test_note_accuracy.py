"""Accuracy evaluation for the audio transcription model.

The task book requires measuring precision / recall / F1, pitch accuracy and
onset/offset error against a reference - "the model returned something" is not
evidence of transcription quality. Fixtures are synthesised with a known ground
truth so the expected notes are exact.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path
from typing import List, Sequence, Tuple

import pytest

pytest.importorskip("basic_pitch", reason="audio transcription model not installed")  # noqa: E402

from app.services.audio import note_extraction
from app.services.audio.note_extraction import DetectedNote

SAMPLE_RATE = 22050
NOTE_SECONDS = 0.4


def synth(path: Path, notes: Sequence[Tuple[int, float, float]], *, sample_rate: int = SAMPLE_RATE) -> Path:
    """Render ``(pitch, start_seconds, duration_seconds)`` into a mono WAV."""
    total = max(start + length for _pitch, start, length in notes) + 0.2
    samples = [0.0] * int(total * sample_rate)
    for pitch, start, length in notes:
        frequency = 440.0 * 2 ** ((pitch - 69) / 12)
        offset = int(start * sample_rate)
        count = int(length * sample_rate)
        for index in range(count):
            t = index / sample_rate
            envelope = min(1.0, t / 0.02, (length - t) / 0.05)
            value = (
                0.6 * math.sin(2 * math.pi * frequency * t)
                + 0.25 * math.sin(2 * math.pi * 2 * frequency * t)
                + 0.1 * math.sin(2 * math.pi * 3 * frequency * t)
            )
            samples[offset + index] += value * max(0.0, envelope)
    peak = max(1e-9, max(abs(value) for value in samples))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(
            b"".join(
                struct.pack("<h", int(max(-1.0, min(1.0, value / peak * 0.9)) * 32767))
                for value in samples
            )
        )
    return path


def match_notes(
    detected: Sequence[DetectedNote],
    reference: Sequence[Tuple[int, float]],
    *,
    onset_tolerance: float = 0.06,
    pitch_tolerance: int = 0,
) -> Tuple[int, int, int, List[float], List[float]]:
    """Greedy one-to-one matching. Returns (tp, fp, fn, onset_errors, offset_errors)."""
    unmatched = list(detected)
    true_positives = 0
    onset_errors: List[float] = []
    offset_errors: List[float] = []
    for pitch, start in reference:
        best = None
        for candidate in unmatched:
            if abs(candidate.pitch - pitch) > pitch_tolerance:
                continue
            if abs(candidate.start - start) > onset_tolerance:
                continue
            if best is None or abs(candidate.start - start) < abs(best.start - start):
                best = candidate
        if best is not None:
            unmatched.remove(best)
            true_positives += 1
            onset_errors.append(abs(best.start - start))
            offset_errors.append(abs(best.end - (start + NOTE_SECONDS)))
    false_negatives = len(reference) - true_positives
    return true_positives, len(unmatched), false_negatives, onset_errors, offset_errors


def f1(tp: int, fp: int, fn: int) -> float:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


REFERENCE_MELODY = [(60, 0.0), (64, 0.4), (67, 0.8), (72, 1.2)]


@pytest.fixture(scope="module")
def melody_path(tmp_path_factory) -> Path:
    directory = tmp_path_factory.mktemp("accuracy")
    return synth(
        directory / "melody.wav",
        [(pitch, start, NOTE_SECONDS) for pitch, start in REFERENCE_MELODY],
    )


def test_monophonic_melody_accuracy(melody_path):
    detected = note_extraction.transcribe_file(melody_path)
    assert detected, "model produced no notes for a clear melody"

    tp, fp, fn, onset_errors, offset_errors = match_notes(detected, REFERENCE_MELODY)
    score = f1(tp, fp, fn)

    assert score >= 0.9, f"F1={score:.3f} tp={tp} fp={fp} fn={fn}"
    assert tp == len(REFERENCE_MELODY), "every reference note must be found"
    assert max(onset_errors) < 0.06, f"onset error {max(onset_errors):.3f}s"
    assert sum(offset_errors) / len(offset_errors) < 0.12

    pitches = {note.pitch for note in detected}
    assert pitches.issuperset({60, 64, 67, 72}), sorted(pitches)
    assert all(0.0 < note.amplitude <= 1.0 for note in detected)


def test_fast_tempo_melody_accuracy(tmp_path):
    """Sixteenth-note speed: the model must still find the notes."""
    reference = [(pitch, index * 0.15) for index, pitch in enumerate([62, 64, 66, 67])]
    path = synth(tmp_path / "fast.wav", [(p, s, 0.14) for p, s in reference])
    detected = note_extraction.transcribe_file(path, minimum_note_length_ms=40.0)
    tp, fp, fn, _onset, _offset = match_notes(detected, reference, onset_tolerance=0.08)
    assert f1(tp, fp, fn) >= 0.75, f"tp={tp} fp={fp} fn={fn}"


def test_low_register_melody(tmp_path):
    """Lower octave: pitch detection must not be limited to the treble range."""
    reference = [(48, 0.0), (52, 0.4), (55, 0.8)]
    path = synth(tmp_path / "low.wav", [(p, s, NOTE_SECONDS) for p, s in reference])
    detected = note_extraction.transcribe_file(path)
    tp, fp, fn, _onset, _offset = match_notes(detected, reference)
    assert f1(tp, fp, fn) >= 0.9, f"tp={tp} fp={fp} fn={fn}"
    assert {note.pitch for note in detected}.issuperset({48, 52, 55})


def test_chord_polyphony(tmp_path):
    """A three-note chord must come back as simultaneous notes, not one line."""
    chord = [(60, 0.0), (64, 0.0), (67, 0.0)]
    path = synth(tmp_path / "chord.wav", [(p, s, 0.8) for p, s in chord])
    detected = note_extraction.transcribe_file(path)
    assert detected, "no notes for a chord"

    # Polyphony: several distinct pitches must share (almost) the same onset.
    early = [note for note in detected if note.start < 0.08]
    assert len(early) >= 2, [(note.pitch, note.start) for note in detected]
    assert len({note.pitch for note in early}) >= 2, [note.pitch for note in early]
    assert {60, 64, 67} & {note.pitch for note in early}


def test_document_conversion_preserves_musical_data(melody_path):
    detected = note_extraction.transcribe_file(melody_path)
    document = note_extraction.build_document(
        detected, tempo=120.0, title="准确率测试", source_audio_id="asset-test"
    )
    assert len(document.events) == len(detected)
    assert document.tracks[0].track_id == document.events[0].track_id
    assert document.source_metadata.kind == "transcription"
    assert document.source_metadata.recognition_model == note_extraction.MODEL_ID
    for event in document.events:
        assert event.pitch is not None
        assert event.duration > 0
        assert event.confidence is not None and 0 <= event.confidence <= 1
        assert event.measure >= 1
        # quantised to the 1/16 grid
        assert abs(event.start_time * 4 - round(event.start_time * 4)) < 1e-6
    # events are ordered and inside the document duration (seconds, derived from
    # the last beat by the document engine)
    assert document.duration >= max(event.start_time for event in document.events) * 0.4
    assert 1.0 <= document.duration <= 2.5


def test_silence_produces_no_notes(tmp_path):
    path = synth(tmp_path / "silence.wav", [(60, 0.0, 0.5)])
    # overwrite with silence of the same length
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(b"\x00\x00" * int(SAMPLE_RATE * 0.6))
    assert note_extraction.transcribe_file(path) == []


def test_missing_model_raises_instead_of_faking(monkeypatch):
    monkeypatch.setattr(note_extraction, "_load_module", lambda: None)
    assert note_extraction.model_status()["available"] is False
    with pytest.raises(RuntimeError):
        note_extraction.transcribe_file(Path("does-not-exist.wav"))
