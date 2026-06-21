"""Analytics and reporting endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from atved.api import deps
from atved.db.models import ViolationRecord
from atved.schemas.analytics import ViolationStats

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/stats", response_model=ViolationStats)
async def get_stats(
    days: int = 7,
    db: AsyncSession = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
):
    """Get high-level violation statistics."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    
    query = select(ViolationRecord).where(ViolationRecord.detected_at >= cutoff)
    result = await db.execute(query)
    records = result.scalars().all()
    
    by_type = {}
    by_status = {}
    
    for r in records:
        v_type = r.violation_type.value
        v_status = r.status.value
        by_type[v_type] = by_type.get(v_type, 0) + 1
        by_status[v_status] = by_status.get(v_status, 0) + 1
        
    return ViolationStats(
        total=len(records),
        by_type=by_type,
        by_status=by_status,
        by_camera={},  # Implement complex group_by as needed
        date_from=cutoff,
        date_to=datetime.now(timezone.utc)
    )
