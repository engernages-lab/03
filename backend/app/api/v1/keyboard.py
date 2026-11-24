"""Keyboard layout API (owner: pocket-keyboard-mapping skill)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.keyboard import KeyboardLayout, default_layout
from app.services.keyboard import repository

router = APIRouter()


class DuplicateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=40)


class LayoutListResponse(BaseModel):
    items: List[KeyboardLayout]
    total: int


@router.get("", response_model=LayoutListResponse)
def list_layouts(
    include_builtin: bool = Query(default=True), db: Session = Depends(get_db)
) -> LayoutListResponse:
    items = repository.list_layouts(db, include_builtin=include_builtin)
    return LayoutListResponse(items=items, total=len(items))


@router.post("", response_model=KeyboardLayout, status_code=status.HTTP_201_CREATED)
def create_layout(layout: KeyboardLayout, db: Session = Depends(get_db)) -> KeyboardLayout:
    return repository.create_layout(db, layout)


@router.post("/import", response_model=KeyboardLayout, status_code=status.HTTP_201_CREATED)
def import_layout(payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)) -> KeyboardLayout:
    return repository.import_layout(db, payload)


@router.post("/restore-default", response_model=KeyboardLayout)
def restore_default(db: Session = Depends(get_db)) -> KeyboardLayout:
    return repository.restore_default(db)


@router.get("/{layout_id}", response_model=KeyboardLayout)
def get_layout(layout_id: str, db: Session = Depends(get_db)) -> KeyboardLayout:
    return repository.get_layout(db, layout_id)


@router.put("/{layout_id}", response_model=KeyboardLayout)
def update_layout(
    layout_id: str, layout: KeyboardLayout, db: Session = Depends(get_db)
) -> KeyboardLayout:
    return repository.update_layout(db, layout_id, layout)


@router.delete("/{layout_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_layout(layout_id: str, db: Session = Depends(get_db)) -> Response:
    repository.delete_layout(db, layout_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{layout_id}/duplicate", response_model=KeyboardLayout, status_code=status.HTTP_201_CREATED)
def duplicate_layout(
    layout_id: str, payload: Optional[DuplicateRequest] = None, db: Session = Depends(get_db)
) -> KeyboardLayout:
    return repository.duplicate_layout(db, layout_id, payload.name if payload else None)


@router.get("/{layout_id}/preview")
def preview_layout(layout_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return repository.layout_preview(db, layout_id)


@router.get("/{layout_id}/export")
def export_layout(layout_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return repository.export_layout(db, layout_id)


@router.get("/{layout_id}/pitch-map")
def pitch_map(layout_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    layout = repository.get_layout(db, layout_id)
    mapping = repository.layout_preview_map(layout)
    return {"layout_id": layout.layout_id, "mapping": {str(k): v for k, v in sorted(mapping.items())}}
