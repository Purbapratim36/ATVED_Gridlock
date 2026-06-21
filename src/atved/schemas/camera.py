"""Camera management schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from atved.db.models import CameraStatus


class CameraCreate(BaseModel):
    external_id: str = Field(min_length=1, max_length=50)
    location_name: str = Field(max_length=255)
    latitude: float | None = None
    longitude: float | None = None
    stream_url: str = Field(max_length=1024)
    config_json: dict[str, Any] = Field(default_factory=dict)


class CameraResponse(BaseModel):
    id: uuid.UUID
    external_id: str
    location_name: str
    latitude: float | None
    longitude: float | None
    status: CameraStatus
    stream_url: str
    config_json: dict[str, Any]
    installed_at: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class CameraUpdate(BaseModel):
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    stream_url: str | None = None
    config_json: dict[str, Any] | None = None
    status: CameraStatus | None = None


class CameraHealthResponse(BaseModel):
    camera_id: uuid.UUID
    status: CameraStatus
    last_frame_ts: datetime | None = None
    error_count: int = 0
    decode_error_rate: float = 0.0
    frame_drop_rate: float = 0.0
