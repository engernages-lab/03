"""Generate deterministic fixtures for the Playwright end-to-end tests.

Creates:
    tests/fixtures/sample.mid  - 8-bar melody + chord, 100 BPM, 4/4
    tests/fixtures/tone.wav    - 2s 440Hz stereo WAV for upload tests

Run from the repository root:  python scripts/make_fixtures.py
"""

from __future__ import annotations

import io
import math
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def make_midi(path: Path) -> None:
    import mido

    midi = mido.MidiFile(type=1, ticks_per_beat=480, charset="utf-8")
    meta = mido.MidiTrack()
    midi.tracks.append(meta)
    meta.append(mido.MetaMessage("track_name", name="PocketScore Demo", time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=int(60_000_000 / 100), time=0))

    melody = mido.MidiTrack()
    midi.tracks.append(melody)
    melody.append(mido.MetaMessage("track_name", name="主旋律", time=0))

    notes = [
        (60, 0, 1, 96), (62, 1, 1, 90), (64, 2, 1, 88), (65, 3, 1, 84),
        (67, 4, 2, 96), (69, 6, 1, 90), (71, 7, 1, 88),
        (60, 8, 1, 96), (64, 9, 1, 90), (67, 10, 1, 88), (72, 11, 1, 84),
        (71, 12, 2, 94), (67, 14, 2, 90),
        (60, 16, 4, 100),
    ]
    events = []
    for pitch, start, duration, velocity in notes:
        events.append((int(start * 480), 1, mido.Message("note_on", note=pitch, velocity=velocity, channel=0)))
        events.append((int((start + duration) * 480), 0, mido.Message("note_off", note=pitch, velocity=0, channel=0)))
    events.sort(key=lambda item: (item[0], item[1]))
    previous = 0
    for tick, _order, message in events:
        message.time = max(0, tick - previous)
        previous = tick
        melody.append(message)

    buffer = io.BytesIO()
    midi.save(file=buffer)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())
    print(f"wrote {path} ({len(buffer.getvalue())} bytes)")


def make_wav(path: Path, duration: float = 2.0, sample_rate: int = 44100) -> None:
    frames = int(duration * sample_rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        payload = bytearray()
        for index in range(frames):
            envelope = min(1.0, index / (sample_rate * 0.05), (frames - index) / (sample_rate * 0.05))
            value = int(0.45 * 32767 * envelope * math.sin(2 * math.pi * 440 * index / sample_rate))
            payload.extend(struct.pack("<hh", value, value))
        handle.writeframes(bytes(payload))
    print(f"wrote {path} ({path.stat().st_size} bytes)")


def main() -> int:
    make_midi(FIXTURES / "sample.mid")
    make_wav(FIXTURES / "tone.wav")
    return 0


if __name__ == "__main__":
    sys.exit(main())
