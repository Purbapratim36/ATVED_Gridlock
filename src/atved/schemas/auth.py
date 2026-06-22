"""Auth schemas — login, token, staff management."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from atved.db.models import StaffRole


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class StaffCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(max_length=255)
    password: str = Field(min_length=8)
    role: StaffRole


class StaffResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    role: StaffRole
    is_active: bool
    mfa_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class StaffUpdate(BaseModel):
    email: str | None = None
    role: StaffRole | None = None
    is_active: bool | None = None
