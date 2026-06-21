"""Analytics and reporting schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from atved.db.models import ViolationType


class ViolationStats(BaseModel):
    total: int
    by_type: dict[str, int]
    by_status: dict[str, int]
    by_camera: dict[str, int]
    date_from: datetime | None = None
    date_to: datetime | None = None


class TrendDataPoint(BaseModel):
    date: date
    count: int
    violation_type: str | None = None


class HeatmapPoint(BaseModel):
    latitude: float
    longitude: float
    violation_count: int
    violation_types: list[str]


class VehicleHistoryResponse(BaseModel):
    plate_text: str
    total_violations: int
    violations: list[dict[str, Any]]
