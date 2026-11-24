"""Versioned API router aggregation.

Every feature module mounts its router here so the public surface is always
``/api/v1/...``.  Adding a module never changes existing paths.
"""

from fastapi import APIRouter

from app.api.v1 import (
    audio,
    documents,
    eligibility,
    health,
    keyboard,
    library,
    midi,
    notation,
    playback,
    sources,
    transcription,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["system"])
api_router.include_router(documents.router, prefix="/documents", tags=["music-document"])
api_router.include_router(keyboard.router, prefix="/keyboard-layouts", tags=["keyboard"])
api_router.include_router(midi.router, prefix="/midi", tags=["midi"])
api_router.include_router(audio.router, prefix="/audio", tags=["audio"])
api_router.include_router(notation.router, prefix="/notation", tags=["notation"])
api_router.include_router(sources.router, prefix="/sources", tags=["music-sources"])
api_router.include_router(library.router, prefix="/library", tags=["music-library"])
api_router.include_router(playback.router, prefix="/playback", tags=["playback"])
api_router.include_router(eligibility.router, prefix="/eligibility", tags=["eligibility"])
api_router.include_router(transcription.router, prefix="/transcription", tags=["transcription"])

__all__ = ["api_router"]
