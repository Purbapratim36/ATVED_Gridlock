"""Driver / Citizen endpoints for User Dashboard."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from atved.api import deps
from atved.db.models import Driver, RegisteredPlate, ViolationRecord

router = APIRouter(prefix="/drivers", tags=["Drivers"])

# Mock authentication: Just pass driver ID or email in headers/query for demo
@router.get("/profile")
async def get_driver_profile(
    email: str,
    db: AsyncSession = Depends(deps.get_db),
):
    """Get the driver's profile, traffic score, and registered plates."""
    query = select(Driver).where(Driver.email == email)
    result = await db.execute(query)
    driver = result.scalar_one_or_none()
    
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
        
    # Get plates
    plate_query = select(RegisteredPlate).where(RegisteredPlate.driver_id == driver.id)
    plates_result = await db.execute(plate_query)
    plates = [p.plate_text for p in plates_result.scalars().all()]
    
    return {
        "id": driver.id,
        "name": driver.name,
        "email": driver.email,
        "traffic_score": driver.traffic_score,
        "registered_plates": plates
    }


@router.get("/violations")
async def get_driver_violations(
    email: str,
    db: AsyncSession = Depends(deps.get_db),
):
    """Get all violations associated with the driver's registered plates."""
    # Find driver plates
    driver_query = select(Driver).where(Driver.email == email)
    driver = (await db.execute(driver_query)).scalar_one_or_none()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
        
    plate_query = select(RegisteredPlate).where(RegisteredPlate.driver_id == driver.id)
    plates = [p.plate_text for p in (await db.execute(plate_query)).scalars().all()]
    
    if not plates:
        return []
        
    # Fetch violations where decrypted plate matches (for demo we'll use a hack or just return mock if encrypted)
    # Since plate is encrypted in ViolationRecord, we can't easily query by it natively in postgres without the key.
    # For this demo, let's just fetch all violations and decrypt in memory, OR we just store a plain text fallback for the demo.
    
    # Actually, we can just fetch all and filter in Python. It's fine for a demo.
    from atved.core.security import decrypt_pii
    query = select(ViolationRecord).order_by(desc(ViolationRecord.detected_at))
    all_violations = (await db.execute(query)).scalars().all()
    
    driver_violations = []
    for v in all_violations:
        if not v.plate_text_encrypted:
            continue
        try:
            plain_text = decrypt_pii(v.plate_text_encrypted)
            if plain_text in plates:
                driver_violations.append({
                    "id": v.id,
                    "type": v.violation_type.value,
                    "status": v.status.value,
                    "detected_at": v.detected_at,
                    "plate": plain_text,
                    "confidence": v.confidence_score
                })
        except Exception:
            pass
            
    return driver_violations
