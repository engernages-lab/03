"""Model inference stage: Basic Pitch (ONNX on Windows/py3.9, TF elsewhere)."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.services.audio.transcription.config import DetectedNote, TranscriptionConfig

logger = get_logger(__name__)

MODEL_ID = "basic_pitch"
MODEL_NAME = "Basic Pitch"
MODEL_VERSION = "0.4.0"
MODEL_LICENSE = "Apache-2.0"
MODEL_SOURCE = "https://github.com/spotify/basic-pitch"


def load_module():
    try:
        return importlib.import_module("basic_pitch.inference")
    except Exception as exc:  # pragma: no cover - optional install
        logger.warning("basic_pitch is not importable: %s", exc)
        return None


def runtime_version() -> Optional[str]:
    try:
        ort = importlib.import_module("onnxruntime")
        return getattr(ort, "__version__", None)
    except Exception:  # pragma: no cover - optional
        return None


def runtime_name() -> str:
    if runtime_version():
        return "onnxruntime"
    try:
        importlib.import_module("tensorflow")
        return "tensorflow"
    except Exception:  # pragma: no cover
        return "unknown"


def model_status() -> Dict[str, Any]:
    inference = load_module()
    available = inference is not None
    return {
        "available": available,
        "model_id": MODEL_ID,
        "name": MODEL_NAME,
        "version": MODEL_VERSION,
        "license": MODEL_LICENSE,
        "source": MODEL_SOURCE,
        "runtime": f"{runtime_name()} {runtime_version() or ''}".strip() if available else None,
        "polyphonic": True,
        "instrument_scope": ["piano", "keyboard", "melodic instruments", "voice"],
        "outputs": ["pitch", "onset", "offset", "velocity", "note confidence"],
        "capabilities": {
            "monophonic_melody": True,
            "polyphonic": True,
            "piano": True,
            "multi_instrument": False,
            "velocity": True,
            "confidence": True,
            "post_processing": "V1.1-A (harmonic suppression + onset splitting)",
        },
        "reason": (
            None
            if available
            else "basic-pitch 未安装或无法加载；安装命令：pip install basic-pitch"
        ),
    }


def run_model(path: Path, config: TranscriptionConfig) -> List[DetectedNote]:
    """Run the model and return its **raw** note events (no post-processing)."""
    inference = load_module()
    if inference is None:
        raise RuntimeError("basic_pitch_unavailable")

    from basic_pitch import ICASSP_2022_MODEL_PATH

    logger.info("running %s on %s", MODEL_ID, path.name)
    _model_output, _midi_data, note_events = inference.predict(
        str(path),
        ICASSP_2022_MODEL_PATH,
        onset_threshold=config.onset_threshold,
        frame_threshold=config.frame_threshold,
        minimum_note_length=config.minimum_note_length_ms,
        minimum_frequency=config.minimum_frequency,
        maximum_frequency=config.maximum_frequency,
        melodia_trick=config.melodia_trick,
    )

    notes: List[DetectedNote] = []
    for event in note_events:
        start, end, pitch, amplitude = (
            float(event[0]),
            float(event[1]),
            int(event[2]),
            float(event[3]),
        )
        if end <= start:
            continue
        notes.append(
            DetectedNote(
                pitch=max(0, min(127, pitch)),
                start=max(0.0, start),
                end=max(0.0, end),
                amplitude=max(0.0, min(1.0, amplitude)),
                confidence=max(0.0, min(1.0, amplitude)),
                source="model",
            )
        )
    notes.sort(key=lambda note: (note.start, note.pitch))
    if len(notes) > config.max_notes:
        logger.warning("model produced %s notes, truncating to %s", len(notes), config.max_notes)
        notes = notes[: config.max_notes]
    return notes
