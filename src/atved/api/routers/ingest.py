"""Ingestion endpoints for the AI Pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from atved.api import deps
from atved.db.models import ViolationRecord, ViolationType, Camera, ViolationStatus
from atved.core.security import encrypt_pii
from atved.scoring import process_violation_for_driver

router = APIRouter(prefix="/ingest", tags=["Ingest"])

class ViolationIngestRequest(BaseModel):
    camera_external_id: str
    violation_type: ViolationType
    confidence_score: float
    vehicle_type: str
    plate_text: str | None = None
    plate_confidence: float | None = None
    detected_at: datetime | None = None

@router.post("")
async def ingest_violation(
    req: ViolationIngestRequest,
    db: AsyncSession = Depends(deps.get_db),
):
    """Ingest a new violation from the AI pipeline."""
    # Find camera
    cam_query = select(Camera).where(Camera.external_id == req.camera_external_id)
    camera = (await db.execute(cam_query)).scalar_one_or_none()
    
    if not camera:
        # Auto-create camera for demo purposes
        camera = Camera(
            external_id=req.camera_external_id,
            location_name="Demo Camera",
            stream_url="demo",
        )
        db.add(camera)
        await db.commit()
        await db.refresh(camera)
        
    detected_time = req.detected_at or datetime.now(timezone.utc)
    
    # Encrypt plate
    enc_plate = None
    if req.plate_text:
        enc_plate = encrypt_pii(req.plate_text)
        
    record = ViolationRecord(
        camera_id=camera.id,
        violation_type=req.violation_type,
        status=ViolationStatus.PENDING_REVIEW,
        confidence_score=req.confidence_score,
        calibrated_confidence=req.confidence_score,
        vehicle_type=req.vehicle_type,
        plate_text_encrypted=enc_plate,
        plate_confidence=req.plate_confidence,
        detected_at=detected_time
    )
    
    db.add(record)
    
    # Process Traffic Score Deduction if plate is registered
    if req.plate_text:
        await process_violation_for_driver(db, req.plate_text, req.violation_type)
        
    await db.commit()
    await db.refresh(record)
    
    return {"id": record.id, "status": "ingested"}
