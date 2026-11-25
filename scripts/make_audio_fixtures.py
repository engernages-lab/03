"""Generate real compressed-format fixtures for the upload tests.

Uses the FFmpeg binary bundled with ``imageio-ffmpeg`` so the fixtures are
genuine MP3 / FLAC / M4A / OGG / OPUS streams - the upload tests must decode
real audio, not files that merely carry the right extension.
"""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SAMPLE_RATE = 22050
NOTE_SECONDS = 0.4
MELODY = [(60, 0.0), (64, 0.4), (67, 0.8), (72, 1.2)]

TARGETS = {
    "melody.mp3": ["-codec:a", "libmp3lame", "-b:a", "128k"],
    "melody.flac": ["-codec:a", "flac"],
    "melody.m4a": ["-codec:a", "aac", "-b:a", "128k"],
    "melody.ogg": ["-codec:a", "libvorbis", "-q:a", "5"],
    "melody.opus": ["-codec:a", "libopus", "-b:a", "96k"],
}


def build_wav(path: Path) -> Path:
    total = max(start for _pitch, start in MELODY) + NOTE_SECONDS + 0.2
    samples = [0.0] * int(total * SAMPLE_RATE)
    for pitch, start in MELODY:
        frequency = 440.0 * 2 ** ((pitch - 69) / 12)
        offset = int(start * SAMPLE_RATE)
        count = int(NOTE_SECONDS * SAMPLE_RATE)
        for index in range(count):
            t = index / SAMPLE_RATE
            envelope = min(1.0, t / 0.02, (NOTE_SECONDS - t) / 0.05)
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
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(
            b"".join(
                struct.pack("<h", int(max(-1.0, min(1.0, value / peak * 0.9)) * 32767))
                for value in samples
            )
        )
    return path


def ffmpeg_binary() -> str:
    try:
        import imageio_ffmpeg
    except ImportError:  # pragma: no cover - dev dependency
        print("imageio-ffmpeg is required", file=sys.stderr)
        raise SystemExit(2)
    return imageio_ffmpeg.get_ffmpeg_exe()


def main() -> int:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg_binary()
    print(f"ffmpeg: {ffmpeg}")
    with tempfile.TemporaryDirectory() as tmp:
        wav = build_wav(Path(tmp) / "melody.wav")
        print(f"source wav: {wav.stat().st_size} bytes")
        for name, codec_args in TARGETS.items():
            target = FIXTURES / name
            command = [ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), *codec_args, str(target)]
            subprocess.run(command, check=True)
            print(f"  {name}: {target.stat().st_size} bytes")
        shutil.copyfile(wav, FIXTURES / "melody.wav")
        print(f"  melody.wav: {(FIXTURES / 'melody.wav').stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
