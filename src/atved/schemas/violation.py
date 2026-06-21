"""Violation record schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from atved.db.models import ViolationStatus, ViolationType


class ViolationResponse(BaseModel):
    id: uuid.UUID
    camera_id: uuid.UUID
    violation_type: ViolationType
    status: ViolationStatus
    confidence_score: float
    calibrated_confidence: float
    vehicle_type: str
    vehicle_color: str | None
    plate_text: str | None = None  # Decrypted at API layer
    plate_confidence: float | None
    reviewer_id: uuid.UUID | None
    reviewed_at: datetime | None
    decision_notes: str | None
    detected_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ViolationReviewRequest(BaseModel):
    """Human review decision — the core human-in-the-loop gate."""

    status: ViolationStatus = Field(
        description="Must be CONFIRMED or DISMISSED"
    )
    decision_notes: str = Field(
        min_length=1,
        max_length=2000,
        description="Reviewer must provide reasoning",
    )


class ViolationFilterParams(BaseModel):
    violation_type: ViolationType | None = None
    status: ViolationStatus | None = None
    camera_id: uuid.UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_confidence: float | None = None
