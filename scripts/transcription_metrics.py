"""Print real transcription metrics for the report (no fabricated numbers)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "tests"))

import tempfile  # noqa: E402

from test_note_accuracy import (  # noqa: E402
    NOTE_SECONDS,
    REFERENCE_MELODY,
    f1,
    match_notes,
    synth,
)

from app.services.audio import note_extraction  # noqa: E402


def report(label: str, notes, reference, duration, tolerance=0.06):
    detected = note_extraction.transcribe_file(notes)
    tp, fp, fn, onset, offset = match_notes(detected, reference, onset_tolerance=tolerance)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    print(f"{label}")
    print(f"  reference notes : {len(reference)}")
    print(f"  detected notes  : {len(detected)}")
    print(f"  TP/FP/FN        : {tp}/{fp}/{fn}")
    print(f"  precision       : {precision:.3f}")
    print(f"  recall          : {recall:.3f}")
    print(f"  F1              : {f1(tp, fp, fn):.3f}")
    if onset:
        print(f"  onset err mean  : {sum(onset)/len(onset)*1000:.0f} ms (max {max(onset)*1000:.0f} ms)")
    if offset:
        print(f"  offset err mean : {sum(offset)/len(offset)*1000:.0f} ms")
    pitches = sorted({note.pitch for note in detected})
    print(f"  pitches         : {pitches}")
    print()


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    melody = synth(tmp / "melody.wav", [(p, s, NOTE_SECONDS) for p, s in REFERENCE_MELODY])
    report("C 大调四音旋律 (C4 E4 G4 C5, 0.4s/音)", melody, REFERENCE_MELODY, 1.8)

    fast_ref = [(62, i * 0.15) for i, _ in enumerate(range(4))]
    fast = synth(tmp / "fast.wav", [(p, s, 0.14) for p, s in fast_ref])
    report("快速旋律 (D4 E4 F#4 G4, 0.15s/音)", fast, fast_ref, 0.75, tolerance=0.08)

    low_ref = [(48, 0.0), (52, 0.4), (55, 0.8)]
    low = synth(tmp / "low.wav", [(p, s, NOTE_SECONDS) for p, s in low_ref])
    report("低音区 (C3 E3 G3)", low, low_ref, 1.2)

    chord_ref = [(60, 0.0), (64, 0.0), (67, 0.0)]
    chord = synth(tmp / "chord.wav", [(p, s, 0.8) for p, s in chord_ref])
    report("三音和弦 (C4 E4 G4 同时)", chord, chord_ref, 0.8)

    model = note_extraction.model_status()
    print("model:", model["name"], model["version"], "| runtime:", model["runtime"])
    print("license:", model["license"])
    print("polyphonic:", model["polyphonic"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
