"""
Core violation service.

Handles storing new violations from the inference pipeline,
including PII encryption, audit logging, and triggering evidence generation.
"""

from __future__ import annotations

import uuid
from typing import Any
import structlog

from sqlalchemy.ext.asyncio import AsyncSession

from atved.db.models import ViolationRecord, ViolationStatus, ViolationType
from atved.core.security import encrypt_pii
from atved.core.audit import AuditWriter
from atved.violations.classifier import TriageResult

logger = structlog.get_logger(__name__)


class ViolationService:
    """Service layer for violation data operations."""
    
    def __init__(self):
        self.audit = AuditWriter()

    async def ingest_violation(
        self,
        session: AsyncSession,
        triage_result: TriageResult,
        plate_text: str | None = None,
        plate_confidence: float | None = None,
    ) -> ViolationRecord:
        """
        Store a new violation candidate.
        
        Applies encryption to the plate text, sets initial status based on
        triage priority, and writes an audit log.
        """
        candidate = triage_result.candidate
        
        encrypted_plate = None
        if plate_text:
            encrypted_plate = encrypt_pii(plate_text)
            
        status = ViolationStatus.PENDING_REVIEW
        if triage_result.priority == "low":
            # Very low confidence might be auto-dismissed or flagged for low-priority queue
            pass # Keep as pending for now
            
        record = ViolationRecord(
            camera_id=uuid.UUID(candidate.camera_id),
            violation_type=candidate.violation_type,
            status=status,
            confidence_score=candidate.raw_confidence,
            calibrated_confidence=candidate.calibrated_confidence,
            detected_at=candidate.timestamp,
            vehicle_type=candidate.evidence_signals.get("vehicle_type", "unknown"),
            plate_text_encrypted=encrypted_plate,
            plate_confidence=plate_confidence,
        )
        
        session.add(record)
        await session.flush() # Get the ID
        
        await self.audit.log_created(
            session,
            entity_type="violation_record",
            entity_id=record.id,
            details={"priority": triage_result.priority}
        )
        
        return record
