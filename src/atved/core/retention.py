"""
Data retention policy enforcement.

Automatically deletes expired data according to configured retention
windows. Handles: non-violation raw frames, expired violation evidence,
PII field nullification, and audit logging of all deletions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from atved.config import RetentionConfig
from atved.core.audit import AuditWriter
from atved.db.models import AuditAction, ActorType, ViolationRecord, ViolationStatus

logger = structlog.get_logger(__name__)


class RetentionEnforcer:
    """
    Enforces data retention policies by identifying and processing
    expired records.

    Deletion strategy:
        1. Query for violation records past the retention window.
        2. Nullify encrypted PII fields (plate_text_encrypted).
        3. Set status to PROCESSING_RESTRICTED (prevents further review).
        4. Delete associated evidence frames from object storage.
        5. Log every deletion in the audit trail.

    Non-violation raw frames are handled by S3 lifecycle policies
    or by the retention worker scanning the raw-frames bucket.
    """

    def __init__(self, config: RetentionConfig) -> None:
        self._config = config
        self._audit = AuditWriter()

    async def get_expired_violations(
        self, session: AsyncSession
    ) -> list[uuid.UUID]:
        """
        Find violation records that have exceeded their retention period.

        Only considers records in terminal states (CONFIRMED, DISMISSED,
        APPEAL_RESOLVED) — records still under review or appeal are never
        auto-deleted.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(
            days=self._config.violation_evidence_days
        )
        terminal_statuses = [
            ViolationStatus.CONFIRMED,
            ViolationStatus.DISMISSED,
            ViolationStatus.APPEAL_RESOLVED,
        ]

        result = await session.execute(
            select(ViolationRecord.id).where(
                ViolationRecord.detected_at < cutoff,
                ViolationRecord.status.in_(terminal_statuses),
                ViolationRecord.status != ViolationStatus.PROCESSING_RESTRICTED,
            )
        )
        return [row[0] for row in result.fetchall()]

    def get_raw_frame_cutoff(self) -> datetime:
        """Return the cutoff timestamp for raw frame deletion."""
        return datetime.now(timezone.utc) - timedelta(
            hours=self._config.raw_buffer_hours
        )

    def get_non_violation_cutoff(self) -> datetime:
        """Return the cutoff timestamp for non-violation frame deletion."""
        return datetime.now(timezone.utc) - timedelta(
            hours=self._config.non_violation_hours
        )

    async def nullify_pii(
        self,
        session: AsyncSession,
        violation_ids: list[uuid.UUID],
    ) -> int:
        """
        Nullify PII fields and restrict processing for expired records.

        Returns the number of records updated.
        """
        if not violation_ids:
            return 0

        result = await session.execute(
            update(ViolationRecord)
            .where(ViolationRecord.id.in_(violation_ids))
            .values(
                plate_text_encrypted=None,
                status=ViolationStatus.PROCESSING_RESTRICTED,
            )
        )
        return result.rowcount

    async def enforce(
        self,
        session: AsyncSession,
        storage_client: Any | None = None,
    ) -> dict[str, int]:
        """
        Run full retention enforcement cycle.

        Parameters
        ----------
        session:
            Active database session.
        storage_client:
            Object storage client for deleting evidence frames.
            If None, only database PII is nullified.

        Returns
        -------
        Summary dict with counts: violations_processed, pii_nullified,
        frames_deleted.
        """
        expired_ids = await self.get_expired_violations(session)

        if not expired_ids:
            logger.info("retention.no_expired_records")
            return {"violations_processed": 0, "pii_nullified": 0, "frames_deleted": 0}

        # Nullify PII in database
        nullified = await self.nullify_pii(session, expired_ids)

        # Log each deletion in audit trail
        for vid in expired_ids:
            await self._audit.log_deleted(
                session,
                entity_type="violation_record",
                entity_id=vid,
                reason=f"retention_policy_exceeded_{self._config.violation_evidence_days}_days",
            )

        # Delete evidence frames from storage
        frames_deleted = 0
        if storage_client is not None:
            for vid in expired_ids:
                try:
                    await storage_client.delete_evidence(str(vid))
                    frames_deleted += 1
                except Exception:
                    logger.exception("retention.storage_delete_failed", violation_id=str(vid))

        await session.commit()

        summary = {
            "violations_processed": len(expired_ids),
            "pii_nullified": nullified,
            "frames_deleted": frames_deleted,
        }
        logger.info("retention.enforcement_complete", **summary)
        return summary
