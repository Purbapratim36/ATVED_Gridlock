"""Camera management endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from atved.api import deps
from atved.db.models import Camera, StaffRole
from atved.schemas.camera import CameraCreate, CameraResponse, CameraUpdate

router = APIRouter(prefix="/cameras", tags=["Cameras"])


@router.get("", response_model=list[CameraResponse])
async def list_cameras(
    db: AsyncSession = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
):
    """List all registered cameras."""
    result = await db.execute(select(Camera))
    return result.scalars().all()


@router.post(
    "", 
    response_model=CameraResponse,
    dependencies=[Depends(deps.require_role([StaffRole.ADMIN, StaffRole.ENGINEER]))]
)
async def create_camera(
    camera_in: CameraCreate,
    db: AsyncSession = Depends(deps.get_db),
):
    """Register a new camera (Admin/Engineer only)."""
    # Check if external_id exists
    result = await db.execute(select(Camera).where(Camera.external_id == camera_in.external_id))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Camera external_id already exists")
        
    camera = Camera(**camera_in.model_dump())
    db.add(camera)
    await db.commit()
    await db.refresh(camera)
    return camera


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
):
    """Get camera details."""
    result = await db.execute(select(Camera).where(Camera.id == camera_id))
    camera = result.scalar_one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera
