"""Audio format validation, probing and decoding.

Owner: pocket-audio-transcription skill.  Probing prefers ``soundfile`` (fast,
no subprocess), then FFmpeg (covers every container), then the stdlib ``wave``
module for plain PCM WAV.  Every failure is reported as a typed error - no
silent fallbacks that pretend a file was analysed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.errors import DependencyMissingError, UnsupportedMediaError, ValidationAppError
from app.core.logging import get_logger

logger = get_logger("pocketscore.audio")

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
}
TARGET_SAMPLE_RATE = 22050


@dataclass
class AudioProbe:
    duration: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    bitrate: Optional[int] = None
    codec: Optional[str] = None
    container: Optional[str] = None
    method: str = "unknown"
    warnings: list = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "duration": round(self.duration, 4),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "bitrate": self.bitrate,
            "codec": self.codec,
            "container": self.container,
            "method": self.method,
            "warnings": list(self.warnings),
        }


def validate_extension(filename: str) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedMediaError(
            f"unsupported audio extension {ext or '(none)'!r}",
            code="UNSUPPORTED_MEDIA_TYPE",
            details={"supported": sorted(SUPPORTED_EXTENSIONS)},
        )
    return ext


def resolve_ffmpeg() -> Optional[str]:
    explicit = os.environ.get("POCKETSCORE_FFMPEG_PATH")
    if explicit and shutil.which(explicit):
        return shutil.which(explicit)
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # pragma: no cover - optional dependency
        return None


def _probe_with_soundfile(path: Path) -> Optional[AudioProbe]:
    try:
        import soundfile as sf

        info = sf.info(str(path))
    except Exception:
        return None
    if not info.frames or not info.samplerate:
        return None
    return AudioProbe(
        duration=float(info.frames) / float(info.samplerate),
        sample_rate=int(info.samplerate),
        channels=int(info.channels),
        codec=info.subtype,
        container=info.format,
        method="soundfile",
    )


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_AUDIO_RE = re.compile(
    r"Stream #\d+:\d+.*?: Audio: ([a-zA-Z0-9_]+).*?, (\d+) Hz, ([^,]+)", re.DOTALL
)
_BITRATE_RE = re.compile(r"bitrate:\s*(\d+)\s*kb/s")


def _probe_with_ffmpeg(path: Path) -> Optional[AudioProbe]:
    ffmpeg = resolve_ffmpeg()
    if not ffmpeg:
        return None
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        timeout=get_settings().ffprobe_timeout_seconds,
        check=False,
    )
    text = (result.stderr or "") + (result.stdout or "")
    duration_match = _DURATION_RE.search(text)
    audio_match = _AUDIO_RE.search(text)
    if not duration_match or not audio_match:
        return None
    hours, minutes, seconds = duration_match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    codec = audio_match.group(1)
    sample_rate = int(audio_match.group(2))
    layout = audio_match.group(3).strip()
    channels = {"mono": 1, "stereo": 2}.get(layout)
    if channels is None:
        channels = 2 if "2 channels" in layout else 1
    bitrate_match = _BITRATE_RE.search(text)
    return AudioProbe(
        duration=duration,
        sample_rate=sample_rate,
        channels=channels,
        bitrate=int(bitrate_match.group(1)) if bitrate_match else None,
        codec=codec,
        container="ffmpeg",
        method="ffmpeg",
    )


def _probe_with_wave(path: Path) -> Optional[AudioProbe]:
    if path.suffix.lower() != ".wav":
        return None
    try:
        import wave

        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            channels = handle.getnchannels()
            width = handle.getsampwidth()
    except Exception:
        return None
    if not rate:
        return None
    return AudioProbe(
        duration=frames / float(rate),
        sample_rate=rate,
        channels=channels,
        bitrate=int(rate * channels * width * 8 / 1000) or None,
        codec=f"pcm_s{width * 8}",
        container="wav",
        method="wave",
    )


def probe_audio(path: Path) -> AudioProbe:
    if not path.exists():
        raise ValidationAppError("audio file does not exist", code="AUDIO_PROBE_FAILED")
    if path.stat().st_size == 0:
        raise ValidationAppError("audio file is empty", code="AUDIO_PROBE_FAILED")

    probe = _probe_with_soundfile(path)
    warnings = []
    if probe is None:
        probe = _probe_with_ffmpeg(path)
        if probe is not None:
            warnings.append("soundfile 无法解析，已使用 FFmpeg 探测")
    if probe is None:
        probe = _probe_with_wave(path)
        if probe is not None:
            warnings.append("已使用标准库 wave 模块探测")
    if probe is None:
        raise ValidationAppError(
            "could not determine audio properties (unsupported codec or corrupt file)",
            code="AUDIO_PROBE_FAILED",
            details={"filename": path.name},
        )
    if probe.duration <= 0:
        raise ValidationAppError("audio duration is zero", code="AUDIO_PROBE_FAILED")
    if probe.duration > 60 * 60 * 3:
        raise ValidationAppError(
            "audio is longer than the 3 hour limit", code="AUDIO_TOO_LONG"
        )
    probe.warnings.extend(warnings)
    return probe


def decode_mono(path: Path, sample_rate: int = TARGET_SAMPLE_RATE):
    """Decode any supported container into a mono float32 numpy array."""
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover
        raise DependencyMissingError("numpy is required for audio decoding") from exc

    ffmpeg = resolve_ffmpeg()
    if ffmpeg:
        with tempfile.TemporaryDirectory(prefix="pocketscore-decode-") as tmp:
            target = Path(tmp) / "decoded.wav"
            command = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(path), "-ac", "1", "-ar", str(sample_rate), "-f", "wav", str(target),
            ]
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=get_settings().ffprobe_timeout_seconds, check=False
            )
            if completed.returncode == 0 and target.exists():
                import soundfile as sf

                audio, sr = sf.read(str(target), dtype="float32", always_2d=False)
                if audio.size:
                    return np.asarray(audio, dtype=np.float32), int(sr)
            logger.warning("ffmpeg decode failed: %s", (completed.stderr or "")[:400])

    try:
        import librosa

        audio, sr = librosa.load(str(path), sr=sample_rate, mono=True)
        return audio.astype("float32"), int(sr)
    except Exception as exc:
        raise ValidationAppError(
            "could not decode the audio file", code="AUDIO_DECODE_FAILED", details={"reason": str(exc)}
        ) from exc


def normalize_peak(audio, target_dbfs: float = -1.0):
    """Peak-normalise to ``target_dbfs`` below full scale."""
    import numpy as np

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak <= 1e-9:
        raise ValidationAppError("audio file is silent", code="AUDIO_SILENT")
    target = 10 ** (target_dbfs / 20.0)
    return np.clip(audio * (target / peak), -1.0, 1.0).astype("float32")


def waveform_buckets(audio, buckets: int = 800):
    """Peak envelope for the UI waveform (real samples, not synthetic)."""
    import numpy as np

    if buckets < 1:
        buckets = 1
    if audio.size == 0:
        return []
    chunk = max(1, audio.size // buckets)
    peaks = []
    for start in range(0, audio.size, chunk):
        window = audio[start : start + chunk]
        if window.size:
            peaks.append(float(np.max(np.abs(window))))
    if len(peaks) > buckets:
        step = len(peaks) / buckets
        peaks = [peaks[int(i * step)] for i in range(buckets)]
    return [round(min(1.0, peak), 4) for peak in peaks]


def analyse(audio, sample_rate: int) -> Dict[str, Any]:
    """Real signal analysis: RMS, onsets, tempo estimate.

    This is *descriptive* audio analysis.  It never emits score notes - note
    extraction requires a model, see TranscriptionJob.
    """
    import numpy as np

    result: Dict[str, Any] = {
        "sample_rate": sample_rate,
        "duration": round(len(audio) / sample_rate, 4),
        "rms": 0.0,
        "peak": 0.0,
        "onsets": 0,
        "bpm": None,
        "beat_count": 0,
        "method": "numpy",
        "warnings": [],
    }
    if audio.size == 0:
        return result

    result["rms"] = round(float(np.sqrt(np.mean(np.square(audio)))), 6)
    result["peak"] = round(float(np.max(np.abs(audio))), 6)

    try:
        import librosa

        onset_frames = librosa.onset.onset_detect(y=audio, sr=sample_rate, backtrack=False)
        result["onsets"] = int(len(onset_frames))
        tempo, beats = librosa.beat.beat_track(y=audio, sr=sample_rate)
        tempo_value = float(np.atleast_1d(tempo)[0])
        if 20.0 <= tempo_value <= 400.0:
            result["bpm"] = round(tempo_value, 2)
        result["beat_count"] = int(len(beats))
        result["method"] = "librosa.beat"
    except Exception as exc:  # pragma: no cover - optional dependency
        result["warnings"].append(f"librosa analysis unavailable: {exc}")

    return result
