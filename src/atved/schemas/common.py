"""
Shared response models used across all API endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response wrapper."""

    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20
    pages: int = 1

    @classmethod
    def create(
        cls, items: list[T], total: int, page: int, page_size: int
    ) -> PaginatedResponse[T]:
        pages = max(1, (total + page_size - 1) // page_size)
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


class ErrorResponse(BaseModel):
    """Standard error response."""

    code: str
    message: str
    details: dict | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    version: str
    uptime_seconds: float | None = None
