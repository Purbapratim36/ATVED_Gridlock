"""Evidence verification schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    violation_record_id: uuid.UUID
    sha256_hash: str
    previous_hash: str | None
    evidence_frames_json: list[dict[str, Any]]
    annotations_json: dict[str, Any]
    metadata_json: dict[str, Any]
    sealed_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class EvidenceVerifyResponse(BaseModel):
    is_valid: bool
    hash_matches: bool
    chain_verified: bool
    details: str | None = None
