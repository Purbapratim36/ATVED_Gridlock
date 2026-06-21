"""
Per-camera health monitor for ATVED ingestion pipeline.

Stores per-camera health counters in **Redis hashes**
(``camera:{camera_id}:health``) and evaluates camera status against
configurable thresholds from ``settings.camera.heartbeat``.

A background asyncio task periodically sweeps all tracked cameras to detect
those that haven't sent a frame within ``timeout_seconds`` and marks them
as ``OFFLINE``.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import redis.asyncio as aioredis
import structlog

from atved.db.models import CameraStatus

if TYPE_CHECKING:
    from atved.config import Settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Redis key helpers
# ---------------------------------------------------------------------------

_KEY_PREFIX = "camera"


def _health_key(camera_id: str) -> str:
    """Return the Redis hash key for a camera's health record."""
    return f"{_KEY_PREFIX}:{camera_id}:health"


def _all_cameras_key() -> str:
    """Return the Redis set key that tracks all known camera IDs."""
    return f"{_KEY_PREFIX}:all_ids"


# ---------------------------------------------------------------------------
# Health fields stored per camera (Redis hash field names)
# ---------------------------------------------------------------------------
_F_STATUS = "status"
_F_LAST_FRAME_TS = "last_frame_ts"
_F_TOTAL_FRAMES = "total_frames"
_F_ERROR_COUNT = "error_count"
_F_DECODE_ERRORS = "decode_errors"
_F_DROPPED_FRAMES = "dropped_frames"


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class CameraHealthMonitor:
    """Redis-backed health tracker for every camera stream.

    Usage::

        monitor = CameraHealthMonitor(settings)
        await monitor.start()

        # On each successful frame capture
        await monitor.record_frame("cam-01")

        # On an error during capture / decode
        await monitor.record_error("cam-01", "decode")

        # Evaluate current health
        status = await monitor.check_health("cam-01")

        await monitor.stop()

    Parameters
    ----------
    settings:
        Application-wide ``Settings`` instance.
    """

    def __init__(self, settings: Settings) -> None:
        self._redis_url: str = settings.redis.url
        self._timeout_s: int = settings.camera.heartbeat.timeout_seconds
        self._degraded_decode_rate: float = settings.camera.heartbeat.degraded_decode_error_rate
        self._degraded_drop_rate: float = settings.camera.heartbeat.degraded_frame_drop_rate
        self._check_interval_s: int = settings.camera.health_check_interval_seconds

        self._redis: aioredis.Redis | None = None
        self._sweep_task: asyncio.Task | None = None
        self._log = logger.bind(component="health_monitor")

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Open the Redis connection and start the background sweep task."""
        self._log.info("health_monitor.starting", redis_url=self._redis_url)
        self._redis = aioredis.from_url(
            self._redis_url,
            decode_responses=True,
            max_connections=10,
        )
        # Verify connectivity
        await self._redis.ping()
        self._sweep_task = asyncio.create_task(
            self._periodic_sweep(), name="camera-health-sweep"
        )
        self._log.info("health_monitor.started")

    async def stop(self) -> None:
        """Cancel the background sweep and close Redis."""
        if self._sweep_task is not None:
            self._sweep_task.cancel()
            try:
                await self._sweep_task
            except asyncio.CancelledError:
                pass
            self._sweep_task = None

        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        self._log.info("health_monitor.stopped")

    # -- public API ----------------------------------------------------------

    async def record_frame(self, camera_id: str) -> None:
        """Record a successfully captured frame for *camera_id*.

        Updates ``last_frame_ts``, increments ``total_frames``, and resets
        the per-camera error count.
        """
        assert self._redis is not None  # noqa: S101
        key = _health_key(camera_id)
        now_ts = str(time.time())

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, _F_LAST_FRAME_TS, now_ts)
            pipe.hincrby(key, _F_TOTAL_FRAMES, 1)
            # Reset transient error count on a good frame
            pipe.hset(key, _F_ERROR_COUNT, "0")
            pipe.hset(key, _F_STATUS, CameraStatus.HEALTHY.value)
            # Track camera ID in the global set
            pipe.sadd(_all_cameras_key(), camera_id)
            await pipe.execute()

        self._log.debug("frame.recorded", camera_id=camera_id)

    async def record_error(
        self,
        camera_id: str,
        error_type: str,
    ) -> None:
        """Record an error event for *camera_id*.

        Parameters
        ----------
        camera_id:
            Which camera experienced the error.
        error_type:
            One of ``"decode"`` or ``"drop"``.  Determines which rate counter
            is incremented.
        """
        assert self._redis is not None  # noqa: S101
        key = _health_key(camera_id)

        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hincrby(key, _F_ERROR_COUNT, 1)
            if error_type == "decode":
                pipe.hincrby(key, _F_DECODE_ERRORS, 1)
            elif error_type == "drop":
                pipe.hincrby(key, _F_DROPPED_FRAMES, 1)
            pipe.sadd(_all_cameras_key(), camera_id)
            await pipe.execute()

        self._log.debug(
            "error.recorded",
            camera_id=camera_id,
            error_type=error_type,
        )

    async def check_health(self, camera_id: str) -> CameraStatus:
        """Evaluate and return the current health status for *camera_id*.

        The evaluation rules (in priority order):

        1. **OFFLINE** — no frame received within ``timeout_seconds``.
        2. **DEGRADED** — decode-error rate or frame-drop rate exceeds the
           configured thresholds.
        3. **HEALTHY** — otherwise.

        Note: ``TAMPERED`` status is set externally by the tamper-detection
        module and is respected (not overwritten) by this method.
        """
        assert self._redis is not None  # noqa: S101
        key = _health_key(camera_id)
        data = await self._redis.hgetall(key)

        if not data:
            return CameraStatus.OFFLINE

        # Respect externally-set tamper status
        current_status = data.get(_F_STATUS, CameraStatus.OFFLINE.value)
        if current_status == CameraStatus.TAMPERED.value:
            return CameraStatus.TAMPERED

        # Rule 1: timeout
        last_ts = float(data.get(_F_LAST_FRAME_TS, "0"))
        if (time.time() - last_ts) > self._timeout_s:
            await self._redis.hset(key, _F_STATUS, CameraStatus.OFFLINE.value)
            return CameraStatus.OFFLINE

        # Rule 2: error rates
        total_frames = int(data.get(_F_TOTAL_FRAMES, "0"))
        if total_frames > 0:
            decode_errors = int(data.get(_F_DECODE_ERRORS, "0"))
            dropped_frames = int(data.get(_F_DROPPED_FRAMES, "0"))

            decode_rate = decode_errors / total_frames
            drop_rate = dropped_frames / total_frames

            if (
                decode_rate >= self._degraded_decode_rate
                or drop_rate >= self._degraded_drop_rate
            ):
                await self._redis.hset(key, _F_STATUS, CameraStatus.DEGRADED.value)
                self._log.warning(
                    "camera.degraded",
                    camera_id=camera_id,
                    decode_error_rate=round(decode_rate, 4),
                    frame_drop_rate=round(drop_rate, 4),
                )
                return CameraStatus.DEGRADED

        # Rule 3: healthy
        await self._redis.hset(key, _F_STATUS, CameraStatus.HEALTHY.value)
        return CameraStatus.HEALTHY

    async def set_tampered(self, camera_id: str) -> None:
        """Mark a camera as tampered (called from tamper-detection logic)."""
        assert self._redis is not None  # noqa: S101
        key = _health_key(camera_id)
        await self._redis.hset(key, _F_STATUS, CameraStatus.TAMPERED.value)
        self._log.critical(
            "camera.tampered",
            camera_id=camera_id,
        )

    async def get_all_statuses(self) -> dict[str, CameraStatus]:
        """Return ``{camera_id: CameraStatus}`` for every tracked camera."""
        assert self._redis is not None  # noqa: S101
        camera_ids: set[str] = await self._redis.smembers(_all_cameras_key())
        statuses: dict[str, CameraStatus] = {}
        for cid in camera_ids:
            statuses[cid] = await self.check_health(cid)
        return statuses

    # -- background sweep ----------------------------------------------------

    async def _periodic_sweep(self) -> None:
        """Periodically evaluate every tracked camera for timeout.

        Runs forever (until cancelled) with a sleep of
        ``health_check_interval_seconds`` between iterations.
        """
        self._log.info(
            "health_sweep.started",
            interval_s=self._check_interval_s,
        )
        while True:
            try:
                await asyncio.sleep(self._check_interval_s)
                statuses = await self.get_all_statuses()
                offline = [
                    cid for cid, st in statuses.items() if st == CameraStatus.OFFLINE
                ]
                if offline:
                    self._log.warning(
                        "health_sweep.cameras_offline",
                        count=len(offline),
                        camera_ids=offline,
                    )
            except asyncio.CancelledError:
                self._log.info("health_sweep.cancelled")
                raise
            except Exception:
                self._log.exception("health_sweep.error")
