"""Appeal workflow schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from atved.db.models import AppealStatus


class AppealCreate(BaseModel):
    violation_record_id: uuid.UUID
    appellant_identifier: str = Field(max_length=255)
    reason: str = Field(min_length=10, max_length=5000)


class AppealResponse(BaseModel):
    id: uuid.UUID
    violation_record_id: uuid.UUID
    reason: str
    status: AppealStatus
    submitted_at: datetime
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    resolution_notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AppealReviewRequest(BaseModel):
    status: AppealStatus = Field(description="Must be UPHELD or OVERTURNED")
    resolution_notes: str = Field(min_length=1, max_length=2000)
