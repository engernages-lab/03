"""Shared response envelopes and pagination primitives."""

from __future__ import annotations

from typing import Generic, List, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: List[T] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0


class DeletedResponse(BaseModel):
    deleted: bool = True
    id: str
