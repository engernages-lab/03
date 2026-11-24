"""Transcription eligibility endpoints."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services import eligibility, library

router = APIRouter()


@router.get("/{track_id}")
def check_track(
    track_id: str,
    confirm_rights: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    result = eligibility.evaluate_by_track_id(db, track_id, user_confirmed_rights=confirm_rights)
    return result.as_dict()


@router.get("")
def check_all(
    track_id: str = Query(..., min_length=1),
    confirm_rights: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Alternate form of the check (kept for query-style clients)."""
    result = eligibility.evaluate_by_track_id(db, track_id, user_confirmed_rights=confirm_rights)
    return result.as_dict()


@router.get("/source/{source_id}")
def source_summary(source_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    library.get_source(db, source_id)
    return eligibility.summarize_for_source(db, source_id)
