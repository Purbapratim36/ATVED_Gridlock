"""
Audit trail writer.

Every state change to violation records, evidence, and PII access
is recorded in the append-only audit log. This module provides a
clean interface for creating audit entries within a database session.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from atved.db.models import AuditAction, AuditLog, ActorType

logger = structlog.get_logger(__name__)


class AuditWriter:
    """
    Writes audit trail entries to the ``audit_logs`` table.

    All methods operate within the caller's session — the caller
    is responsible for committing. This ensures audit writes are
    atomic with the operation they record.
    """

    async def log(
        self,
        session: AsyncSession,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        action: AuditAction,
        actor_type: ActorType,
        actor_id: str,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        hash_at_action: str | None = None,
    ) -> AuditLog:
        """
        Write a single audit log entry.

        Parameters
        ----------
        session:
            Active async database session (caller manages commit/rollback).
        entity_type:
            The type of entity being acted upon (e.g., "violation_record").
        entity_id:
            The UUID of the entity.
        action:
            What happened (CREATED, VIEWED, MODIFIED, etc.).
        actor_type:
            SYSTEM or STAFF.
        actor_id:
            Identifier of the actor (staff UUID or "system").
        details:
            Additional context as a JSON-serialisable dict.
        ip_address:
            Request IP address (for staff actions via API).
        hash_at_action:
            Evidence hash at the time of this action (for chain verification).
        """
        entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_type=actor_type,
            actor_id=actor_id,
            details_json=details or {},
            ip_address=ip_address,
            hash_at_action=hash_at_action,
        )
        session.add(entry)

        logger.info(
            "audit.logged",
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action.value,
            actor=actor_id,
        )
        return entry

    # ── Convenience methods ─────────────────────────────────────────

    async def log_created(
        self,
        session: AsyncSession,
        entity_type: str,
        entity_id: uuid.UUID,
        details: dict[str, Any] | None = None,
        hash_value: str | None = None,
    ) -> AuditLog:
        """Log a CREATED event (typically system-generated)."""
        return await self.log(
            session,
            entity_type=entity_type,
            entity_id=entity_id,
            action=AuditAction.CREATED,
            actor_type=ActorType.SYSTEM,
            actor_id="system",
            details=details,
            hash_at_action=hash_value,
        )

    async def log_viewed(
        self,
        session: AsyncSession,
        entity_type: str,
        entity_id: uuid.UUID,
        staff_id: uuid.UUID,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Log a VIEWED event (staff accessed a record)."""
        return await self.log(
            session,
            entity_type=entity_type,
            entity_id=entity_id,
            action=AuditAction.VIEWED,
            actor_type=ActorType.STAFF,
            actor_id=str(staff_id),
            ip_address=ip_address,
        )

    async def log_reviewed(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        staff_id: uuid.UUID,
        decision: str,
        notes: str | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Log a REVIEWED event (staff made a review decision)."""
        return await self.log(
            session,
            entity_type="violation_record",
            entity_id=entity_id,
            action=AuditAction.REVIEWED,
            actor_type=ActorType.STAFF,
            actor_id=str(staff_id),
            details={"decision": decision, "notes": notes},
            ip_address=ip_address,
        )

    async def log_appealed(
        self,
        session: AsyncSession,
        violation_id: uuid.UUID,
        appeal_id: uuid.UUID,
    ) -> AuditLog:
        """Log an APPEALED event."""
        return await self.log(
            session,
            entity_type="violation_record",
            entity_id=violation_id,
            action=AuditAction.APPEALED,
            actor_type=ActorType.SYSTEM,
            actor_id="system",
            details={"appeal_id": str(appeal_id)},
        )

    async def log_deleted(
        self,
        session: AsyncSession,
        entity_type: str,
        entity_id: uuid.UUID,
        reason: str,
    ) -> AuditLog:
        """Log a DELETED event (retention enforcement)."""
        return await self.log(
            session,
            entity_type=entity_type,
            entity_id=entity_id,
            action=AuditAction.DELETED,
            actor_type=ActorType.SYSTEM,
            actor_id="retention_worker",
            details={"reason": reason},
        )
