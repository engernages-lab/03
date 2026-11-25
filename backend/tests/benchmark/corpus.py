"""Synthetic-but-realistic benchmark corpus for audio transcription.

Every case renders two artefacts from the same note list:

* a WAV (what the model hears)
* a MIDI file (the ground truth, so the reference is an inspectable artefact
  rather than an in-memory list)

Cases are split into ``dev`` (used for tuning) and ``test`` (held out: it must
never influence parameter selection). The split is by case, not by note, and the
two sets use different pitches/rhythms so a tuned constant cannot memorise them.
"""

from __future__ import annotations

import math
import struct
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

SAMPLE_RATE = 22050

# Pitch classes used to keep the two splits disjoint.
DEV_ROOTS = {"mono": 60, "dyad": 62, "triad": 64, "tetrad": 65, "low": 48, "high": 79}
TEST_ROOTS = {"mono": 67, "dyad": 69, "triad": 71, "tetrad": 73, "low": 50, "high": 81}

# Harmonic templates: amplitudes of partials 1..n, plus a decay shape.
TIMBRES: Dict[str, Tuple[List[float], float]] = {
    "sine": ([1.0], 0.0),
    "harmonic": ([1.0, 0.5, 0.25], 0.0),
    "piano": ([1.0, 0.6, 0.35, 0.2, 0.12, 0.07], 2.6),
    "bright": ([1.0, 0.8, 0.6, 0.45, 0.3, 0.2, 0.14, 0.1], 1.2),
}


@dataclass(frozen=True)
class Note:
    pitch: int
    start: float
    duration: float
    velocity: float = 0.8


@dataclass(frozen=True)
class Case:
    name: str
    category: str
    split: str  # "dev" | "test"
    notes: Tuple[Note, ...]
    timbre: str = "harmonic"
    noise_db: float = -60.0
    backing: Tuple[Note, ...] = field(default_factory=tuple)

    @property
    def reference(self) -> List[Tuple[int, float]]:
        return [(note.pitch, note.start) for note in (*self.notes, *self.backing)]

    @property
    def bounds(self) -> List[Tuple[int, float, float]]:
        return [(note.pitch, note.start, note.duration) for note in (*self.notes, *self.backing)]


def _render_voice(samples: List[float], note: Note, timbre: str) -> None:
    partials, decay = TIMBRES[timbre]
    frequency = 440.0 * 2 ** ((note.pitch - 69) / 12)
    offset = int(note.start * SAMPLE_RATE)
    count = int(note.duration * SAMPLE_RATE)
    total = len(samples)
    normaliser = sum(partials) or 1.0
    for index in range(count):
        position = offset + index
        if position >= total:
            break
        t = index / SAMPLE_RATE
        attack = min(1.0, t / 0.008)
        release = min(1.0, max(0.0, (note.duration - t) / 0.03))
        envelope = attack * release
        if decay:
            envelope *= math.exp(-t * decay)
        value = 0.0
        for harmonic, amplitude in enumerate(partials, start=1):
            value += amplitude * math.sin(2 * math.pi * frequency * harmonic * t)
        samples[position] += (value / normaliser) * envelope * note.velocity


def _write_wav(path: Path, samples: Sequence[float]) -> None:
    peak = max(1e-9, max(abs(value) for value in samples))
    scale = 0.9 / peak
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(
            b"".join(
                struct.pack("<h", int(max(-1.0, min(1.0, value * scale)) * 32767))
                for value in samples
            )
        )


def _write_midi(path: Path, notes: Sequence[Note], tempo: float = 120.0) -> None:
    """Write the ground truth as a real MIDI file (ticks from seconds)."""
    try:
        import mido
    except ImportError:  # pragma: no cover - mido is a runtime dependency
        return
    ticks_per_beat = 480
    midi = mido.MidiFile(ticks_per_beat=ticks_per_beat, charset="utf-8")
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo), time=0))
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))

    # (tick, order, note, velocity); note_off (0) sorts before note_on (1)
    events: List[Tuple[int, int, int, int]] = []
    for note in notes:
        start_tick = int(round(note.start * tempo / 60.0 * ticks_per_beat))
        end_tick = int(round((note.start + note.duration) * tempo / 60.0 * ticks_per_beat))
        velocity = max(1, min(127, int(note.velocity * 127)))
        events.append((start_tick, 1, note.pitch, velocity))
        events.append((end_tick, 0, note.pitch, 0))

    previous_tick = 0
    for tick, order, pitch, velocity in sorted(events):
        delta = max(0, tick - previous_tick)
        previous_tick = tick
        if order == 1:
            track.append(mido.Message("note_on", note=pitch, velocity=velocity, time=delta))
        else:
            track.append(mido.Message("note_off", note=pitch, velocity=0, time=delta))
    track.append(mido.MetaMessage("end_of_track", time=0))
    midi.save(str(path))


def build_case(case: Case, directory: Path) -> Dict[str, object]:
    """Render one case to disk and return its metadata."""
    total = 0.3
    for note in case.notes:
        total = max(total, note.start + note.duration + 0.35)
    for note in case.backing:
        total = max(total, note.start + note.duration + 0.2)
    samples = [0.0] * int(total * SAMPLE_RATE)
    for note in case.notes:
        _render_voice(samples, note, case.timbre)
    for note in case.backing:
        # accompaniment sits ~12 dB below the melody
        quieter = Note(note.pitch, note.start, note.duration, note.velocity * 0.25)
        _render_voice(samples, quieter, "sine")

    if case.noise_db > -59.0:
        amplitude = 10 ** (case.noise_db / 20.0)
        seed = 12345
        for index in range(len(samples)):
            seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
            samples[index] += ((seed / 0x7FFFFFFF) * 2 - 1) * amplitude

    directory.mkdir(parents=True, exist_ok=True)
    wav = directory / f"{case.name}.wav"
    midi = directory / f"{case.name}.mid"
    _write_wav(wav, samples)
    _write_midi(midi, list(case.notes) + list(case.backing))
    return {
        "name": case.name,
        "category": case.category,
        "split": case.split,
        "wav": wav,
        "midi": midi,
        "reference": case.reference,
        "bounds": case.bounds,
        "duration": total,
    }


def _melody(root: int, offsets: Sequence[int], step: float, duration: float, velocity: float = 0.8) -> Tuple[Note, ...]:
    return tuple(
        Note(root + offset, index * step, duration, velocity)
        for index, offset in enumerate(offsets)
    )


def dev_cases() -> List[Case]:
    roots = DEV_ROOTS
    return [
        Case("dev_mono", "monophonic", "dev", _melody(roots["mono"], [0, 4, 7, 12], 0.4, 0.4), "harmonic"),
        Case("dev_mono_piano", "monophonic", "dev", _melody(roots["mono"], [0, 2, 4, 5, 7], 0.45, 0.4), "piano"),
        Case("dev_dyad", "dyad", "dev", tuple(
            Note(roots["dyad"] + interval, index * 0.5, 0.45)
            for index, interval in enumerate([0, 5]) for _ in [0]
        ) + tuple(
            Note(roots["dyad"] + interval + 0, index * 0.5, 0.45)
            for index, interval in enumerate([7, 12])
        ), "harmonic"),
        Case("dev_triad", "triad", "dev", tuple(
            Note(roots["triad"] + offset, 0.0, 0.8) for offset in (0, 4, 7)
        ), "harmonic"),
        Case("dev_triad_piano", "triad", "dev", tuple(
            Note(roots["triad"] + offset, 0.0, 0.9) for offset in (0, 3, 7)
        ), "piano"),
        Case("dev_tetrad", "tetrad", "dev", tuple(
            Note(roots["tetrad"] + offset, 0.0, 0.9) for offset in (0, 4, 7, 11)
        ), "piano"),
        Case("dev_low", "low_register", "dev", _melody(roots["low"], [0, 4, 7], 0.4, 0.4), "harmonic"),
        Case("dev_high", "high_register", "dev", _melody(roots["high"], [0, -3, -7], 0.4, 0.4), "harmonic"),
        Case("dev_fast_015", "fast_015", "dev", _melody(roots["mono"] + 2, [0, 2, 4, 5, 7, 9], 0.15, 0.13), "harmonic"),
        Case("dev_fast_020", "fast_020", "dev", _melody(roots["mono"] + 2, [0, 2, 4, 5, 7, 9], 0.20, 0.18), "harmonic"),
        Case("dev_fast_030", "fast_030", "dev", _melody(roots["mono"] + 2, [0, 2, 4, 5], 0.30, 0.28), "harmonic"),
        Case("dev_slow_040", "slow_040", "dev", _melody(roots["mono"] + 2, [0, 4, 7], 0.40, 0.38), "harmonic"),
        Case("dev_velocity", "velocity", "dev", (
            Note(roots["mono"], 0.0, 0.4, 0.25),
            Note(roots["mono"] + 4, 0.4, 0.4, 0.55),
            Note(roots["mono"] + 7, 0.8, 0.4, 0.95),
        ), "harmonic"),
        Case("dev_timbre_bright", "timbre", "dev", _melody(roots["mono"], [0, 4, 7], 0.4, 0.4), "bright"),
        Case("dev_noisy", "noise", "dev", _melody(roots["mono"], [0, 4, 7], 0.4, 0.4), "harmonic", noise_db=-26.0),
        Case("dev_backing", "accompaniment", "dev", _melody(roots["mono"] + 12, [0, 4, 7], 0.5, 0.45), "piano",
             backing=(Note(roots["mono"] - 12, 0.0, 1.5, 0.6), Note(roots["mono"] - 5, 0.0, 1.5, 0.5))),
        # --- hard cases: repeated pitch, legato overlap, genuine octaves ---
        Case("dev_repeat_015", "repeat_015", "dev",
             tuple(Note(roots["mono"] + 4, index * 0.15, 0.13) for index in range(6)), "harmonic"),
        Case("dev_repeat_020", "repeat_020", "dev",
             tuple(Note(roots["mono"] + 4, index * 0.20, 0.18) for index in range(5)), "harmonic"),
        Case("dev_legato", "legato", "dev", tuple(
            Note(roots["mono"] + offset, index * 0.25, 0.4)
            for index, offset in enumerate([0, 2, 4, 5])
        ), "piano"),
        Case("dev_octave_true", "octave_true", "dev", (
            Note(roots["mono"] - 12, 0.0, 0.8, 0.85), Note(roots["mono"], 0.0, 0.8, 0.85),
        ), "piano"),
        Case("dev_fifth_true", "fifth_true", "dev", (
            Note(roots["mono"] - 12, 0.0, 0.8, 0.8), Note(roots["mono"] - 5, 0.0, 0.8, 0.8),
        ), "piano"),
    ]


def test_cases() -> List[Case]:
    """Held-out set: different roots, rhythms and voicings from ``dev``."""
    roots = TEST_ROOTS
    return [
        Case("test_mono", "monophonic", "test", _melody(roots["mono"], [0, 3, 5, 8], 0.42, 0.38), "harmonic"),
        Case("test_mono_piano", "monophonic", "test", _melody(roots["mono"], [0, -2, 3, 5, 7], 0.38, 0.36), "piano"),
        Case("test_dyad", "dyad", "test", (
            Note(roots["dyad"], 0.0, 0.6), Note(roots["dyad"] + 7, 0.0, 0.6),
            Note(roots["dyad"] + 3, 0.7, 0.6), Note(roots["dyad"] + 10, 0.7, 0.6),
        ), "harmonic"),
        Case("test_triad", "triad", "test", tuple(
            Note(roots["triad"] + offset, 0.0, 0.75) for offset in (0, 4, 7)
        ), "harmonic"),
        Case("test_triad_minor", "triad", "test", tuple(
            Note(roots["triad"] + offset, 0.0, 0.85) for offset in (0, 3, 7)
        ), "piano"),
        Case("test_tetrad", "tetrad", "test", tuple(
            Note(roots["tetrad"] + offset, 0.0, 0.95) for offset in (0, 3, 7, 10)
        ), "piano"),
        Case("test_low", "low_register", "test", _melody(roots["low"], [0, 5, 7], 0.45, 0.42), "harmonic"),
        Case("test_high", "high_register", "test", _melody(roots["high"], [0, -4, -7], 0.42, 0.4), "harmonic"),
        Case("test_fast_015", "fast_015", "test", _melody(roots["mono"] - 3, [0, 2, 3, 5, 7, 8], 0.15, 0.13), "harmonic"),
        Case("test_fast_020", "fast_020", "test", _melody(roots["mono"] - 3, [0, 2, 3, 5, 7, 8], 0.20, 0.18), "harmonic"),
        Case("test_fast_030", "fast_030", "test", _melody(roots["mono"] - 3, [0, 2, 3, 5], 0.30, 0.28), "harmonic"),
        Case("test_slow_040", "slow_040", "test", _melody(roots["mono"] - 3, [0, 5, 8], 0.40, 0.38), "harmonic"),
        Case("test_velocity", "velocity", "test", (
            Note(roots["mono"] - 5, 0.0, 0.4, 0.3),
            Note(roots["mono"] - 1, 0.4, 0.4, 0.6),
            Note(roots["mono"] + 2, 0.8, 0.4, 0.9),
        ), "harmonic"),
        Case("test_timbre_bright", "timbre", "test", _melody(roots["mono"], [0, 3, 7], 0.4, 0.4), "bright"),
        Case("test_noisy", "noise", "test", _melody(roots["mono"], [0, 3, 7], 0.4, 0.4), "harmonic", noise_db=-24.0),
        Case("test_backing", "accompaniment", "test", _melody(roots["mono"] + 12, [0, 3, 7], 0.5, 0.45), "piano",
             backing=(Note(roots["mono"] - 12, 0.0, 1.5, 0.6), Note(roots["mono"] - 5, 0.0, 1.5, 0.5))),
        # --- hard cases (different pitches/rhythms from dev) ---
        Case("test_repeat_015", "repeat_015", "test",
             tuple(Note(roots["mono"] - 5, index * 0.15, 0.13) for index in range(6)), "harmonic"),
        Case("test_repeat_020", "repeat_020", "test",
             tuple(Note(roots["mono"] - 5, index * 0.21, 0.19) for index in range(5)), "harmonic"),
        Case("test_legato", "legato", "test", tuple(
            Note(roots["mono"] - 7 + offset, index * 0.26, 0.42)
            for index, offset in enumerate([0, 3, 5, 8])
        ), "piano"),
        Case("test_octave_true", "octave_true", "test", (
            Note(roots["mono"] - 12, 0.0, 0.85, 0.85), Note(roots["mono"], 0.0, 0.85, 0.85),
        ), "piano"),
        Case("test_fifth_true", "fifth_true", "test", (
            Note(roots["mono"] - 12, 0.0, 0.85, 0.8), Note(roots["mono"] - 5, 0.0, 0.85, 0.8),
        ), "piano"),
    ]


def all_cases() -> List[Case]:
    return dev_cases() + test_cases()


def build_corpus(directory: Path, split: str | None = None) -> List[Dict[str, object]]:
    cases = all_cases() if split is None else [case for case in all_cases() if case.split == split]
    return [build_case(case, directory) for case in cases]


if __name__ == "__main__":  # pragma: no cover - manual helper
    import tempfile

    target = Path(tempfile.mkdtemp(prefix="pocketscore-corpus-"))
    built = build_corpus(target)
    print(f"built {len(built)} cases in {target}")
    for item in built:
        print(" ", item["name"], item["category"], item["split"], Path(item["wav"]).stat().st_size)
