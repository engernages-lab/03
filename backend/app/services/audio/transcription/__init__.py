"""Audio transcription package: inference, post-processing and conversion."""

from app.services.audio.transcription.config import (
    DetectedNote,
    TranscriptionConfig,
    TranscriptionResult,
)
from app.services.audio.transcription.inference import (
    MODEL_ID,
    MODEL_LICENSE,
    MODEL_NAME,
    MODEL_SOURCE,
    MODEL_VERSION,
    model_status,
    run_model,
)
from app.services.audio.transcription.pipeline import transcribe

__all__ = [
    "DetectedNote",
    "TranscriptionConfig",
    "TranscriptionResult",
    "MODEL_ID",
    "MODEL_NAME",
    "MODEL_VERSION",
    "MODEL_LICENSE",
    "MODEL_SOURCE",
    "model_status",
    "run_model",
    "transcribe",
]
