"""
Redis deduplication logic to prevent spamming the API with duplicate violations.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

def is_duplicate(redis_client, camera_id: str, plate: str, violation_type: str) -> bool:
    """
    Check if a violation for this plate/camera/type has already been recorded recently.
    Returns True if it's a duplicate (should be suppressed).
    Returns False if it's a new violation (should be sent).
    """
    if redis_client is None:
        return False

    key = f"violation:{camera_id}:{violation_type}:{plate}"
    
    try:
        if redis_client.exists(key):
            return True
            
        # 1800s TTL = 30 minutes suppression window
        redis_client.setex(key, 1800, "1")
        return False
    except Exception as e:
        logger.error("redis.dedup_error", error=str(e), key=key)
        # Fail open
        return False
