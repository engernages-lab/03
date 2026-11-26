"""Generate a long MIDI fixture (many measures) for export performance tests.

The file is deterministic so the E2E expectations (page counts) stay stable.

Usage:  python scripts/make_long_midi.py
"""

from __future__ import annotations

from pathlib import Path

import mido

TICKS_PER_BEAT = 480
MEASURES = 64
BEATS_PER_MEASURE = 4
TEMPO_BPM = 120
OUTPUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "long.mid"

# a simple 8th-note pattern that stays inside one octave
PATTERN = [0, 4, 7, 12, 7, 4, 0, 7]


def main() -> None:
    midi = mido.MidiFile(ticks_per_beat=TICKS_PER_BEAT, charset="utf-8")
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(TEMPO_BPM), time=0))
    track.append(mido.MetaMessage("time_signature", numerator=BEATS_PER_MEASURE, denominator=4, time=0))
    track.append(mido.MetaMessage("track_name", name="PocketScore 长谱面导出测试", time=0))

    root = 60
    for measure in range(MEASURES):
        for index in range(BEATS_PER_MEASURE * 2):  # 8th notes
            pitch = root + PATTERN[index % len(PATTERN)] + (measure % 5) - 2
            track.append(mido.Message("note_on", note=pitch, velocity=88, time=0))
            track.append(mido.Message("note_off", note=pitch, velocity=0, time=TICKS_PER_BEAT // 2))

    track.append(mido.MetaMessage("end_of_track", time=0))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    midi.save(str(OUTPUT))
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size} bytes, {MEASURES} measures)")


if __name__ == "__main__":
    main()
