"""
Retention worker daemon.

Periodically scans for expired violation records and non-violation
raw frames, enforcing the retention policy to meet compliance laws.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import structlog

from atved.config import settings
from atved.db.session import async_session_maker
from atved.core.retention import RetentionEnforcer
from atved.evidence.storage import EvidenceStorage

logger = structlog.get_logger(__name__)


class RetentionWorker:
    """Background task that runs the retention enforcer on a schedule."""
    
    def __init__(self, enforcer: RetentionEnforcer, storage: EvidenceStorage):
        self.enforcer = enforcer
        self.storage = storage
        self._running = False
        
    async def start(self, interval_seconds: int = 3600):
        """Start the retention loop (default runs once an hour)."""
        logger.info("retention_worker.starting", interval_seconds=interval_seconds)
        self._running = True
        
        while self._running:
            try:
                await self._run_cycle()
            except Exception:
                logger.exception("retention_worker.cycle_failed")
                
            await asyncio.sleep(interval_seconds)
            
    def stop(self):
        self._running = False
        
    async def _run_cycle(self):
        """Run one enforcement cycle."""
        logger.info("retention_worker.cycle_started")
        
        async with async_session_maker() as session:
            summary = await self.enforcer.enforce(session, self.storage)
            logger.info("retention_worker.cycle_completed", **summary)
