"""Violation review and retrieval endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc

from atved.api import deps
from atved.db.models import ViolationRecord, ViolationStatus, StaffRole
from atved.schemas.violation import ViolationResponse, ViolationReviewRequest, ViolationFilterParams
from atved.schemas.common import PaginatedResponse
from atved.core.security import decrypt_pii
from atved.core.audit import AuditWriter

router = APIRouter(prefix="/violations", tags=["Violations"])


@router.get("", response_model=PaginatedResponse[ViolationResponse])
async def list_violations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: ViolationStatus | None = None,
    db: AsyncSession = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
    audit: AuditWriter = Depends(deps.get_audit_writer),
):
    """List violations with optional filtering."""
    query = select(ViolationRecord).order_by(desc(ViolationRecord.detected_at))
    if status:
        query = query.where(ViolationRecord.status == status)
        
    # Count total
    from sqlalchemy import func
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar_one()
    
    # Pagination
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    records = result.scalars().all()
    
    # Decrypt plate text for display (only if authorized)
    responses = []
    for record in records:
        resp = ViolationResponse.model_validate(record)
        if record.plate_text_encrypted and current_user.role in [StaffRole.REVIEWER, StaffRole.ADMIN, StaffRole.COMPLIANCE]:
            resp.plate_text = decrypt_pii(record.plate_text_encrypted)
        responses.append(resp)
        
    return PaginatedResponse.create(responses, total, page, page_size)


@router.get("/{violation_id}", response_model=ViolationResponse)
async def get_violation(
    violation_id: uuid.UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
    audit: AuditWriter = Depends(deps.get_audit_writer),
):
    """Get single violation details."""
    result = await db.execute(select(ViolationRecord).where(ViolationRecord.id == violation_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Violation not found")
        
    # Audit log the view event
    await audit.log_viewed(db, "violation_record", violation_id, current_user.id)
    await db.commit()
    
    resp = ViolationResponse.model_validate(record)
    if record.plate_text_encrypted and current_user.role in [StaffRole.REVIEWER, StaffRole.ADMIN, StaffRole.COMPLIANCE]:
        resp.plate_text = decrypt_pii(record.plate_text_encrypted)
        
    return resp


@router.post(
    "/{violation_id}/review", 
    response_model=ViolationResponse,
    dependencies=[Depends(deps.require_role([StaffRole.REVIEWER, StaffRole.ADMIN]))]
)
async def review_violation(
    violation_id: uuid.UUID,
    review: ViolationReviewRequest,
    db: AsyncSession = Depends(deps.get_db),
    current_user = Depends(deps.get_current_user),
    audit: AuditWriter = Depends(deps.get_audit_writer),
):
    """Human-in-the-loop review decision."""
    result = await db.execute(
        select(ViolationRecord).where(
            ViolationRecord.id == violation_id,
            ViolationRecord.status == ViolationStatus.PENDING_REVIEW
        ).with_for_update()
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Violation not found or not in PENDING_REVIEW state")
        
    import datetime
    record.status = review.status
    record.reviewer_id = current_user.id
    record.reviewed_at = datetime.datetime.now(datetime.timezone.utc)
    record.decision_notes = review.decision_notes
    
    await audit.log_reviewed(
        db, violation_id, current_user.id, 
        review.status.value, review.decision_notes
    )
    
    await db.commit()
    await db.refresh(record)
    return record
