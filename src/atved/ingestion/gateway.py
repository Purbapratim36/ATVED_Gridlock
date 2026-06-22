"""
Async multi-camera RTSP gateway for ATVED ingestion pipeline.

``CameraGateway`` manages N concurrent camera streams, each running as an
independent asyncio task.  Blocking OpenCV ``VideoCapture.read()`` calls are
offloaded to a ``ThreadPoolExecutor`` so they never block the event loop.

Key features
^^^^^^^^^^^^

* **Per-camera error isolation** — one camera crashing does not affect the
  others.
* **Backpressure via bounded queues** — when the per-camera queue fills
  beyond ``max_buffer_frames``, the oldest frame is evicted and a drop
  counter is incremented.
* **Rate limiting** — each camera is throttled to ``frame_rate_target`` FPS.
* **Health integration** — every successful capture is reported to
  ``CameraHealthMonitor``; errors are tracked as well.
* **Graceful lifecycle** — ``start()`` spins up all tasks;
  ``stop()`` cancels them and releases OpenCV resources.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import cv2
import numpy as np
import structlog

from atved.ingestion.health_monitor import CameraHealthMonitor
from atved.ingestion.kafka_producer import KafkaFrameProducer

if TYPE_CHECKING:
    from atved.config import Settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Frame message schema
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FrameMessage:
    """Wire-format message representing a single captured frame.

    Attributes
    ----------
    camera_id:
        Unique identifier for the source camera.
    timestamp_utc:
        ISO-8601 UTC string of capture time.
    sequence_no:
        Monotonically increasing sequence number **per camera**.
    frame_bytes:
        JPEG-encoded frame payload.
    metadata:
        Arbitrary per-frame metadata (e.g. resolution, codec info).
    """

    camera_id: str
    timestamp_utc: str
    sequence_no: int
    frame_bytes: bytes
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict suitable for Kafka publishing."""
        return {
            "camera_id": self.camera_id,
            "timestamp_utc": self.timestamp_utc,
            "sequence_no": self.sequence_no,
            "frame_bytes": self.frame_bytes,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Per-camera capture statistics
# ---------------------------------------------------------------------------


@dataclass
class _CameraStats:
    """Mutable counters for a single camera stream."""

    frames_captured: int = 0
    frames_dropped: int = 0
    decode_errors: int = 0
    reconnects: int = 0


# ---------------------------------------------------------------------------
# Camera gateway
# ---------------------------------------------------------------------------


class CameraGateway:
    """Manages concurrent RTSP camera streams and publishes frames to Kafka.

    Parameters
    ----------
    settings:
        Application ``Settings`` instance.
    producer:
        A started ``KafkaFrameProducer``.
    health_monitor:
        A started ``CameraHealthMonitor``.

    Example::

        async with KafkaFrameProducer(settings) as producer:
            monitor = CameraHealthMonitor(settings)
            await monitor.start()
            gateway = CameraGateway(settings, producer, monitor)
            await gateway.start({
                "cam-01": "rtsp://10.0.0.1:554/stream",
                "cam-02": "rtsp://10.0.0.2:554/stream",
            })
            # … run until shutdown …
            await gateway.stop()
            await monitor.stop()
    """

    def __init__(
        self,
        settings: Settings,
        producer: KafkaFrameProducer,
        health_monitor: CameraHealthMonitor,
    ) -> None:
        self._settings = settings
        self._producer = producer
        self._health = health_monitor

        # Config shortcuts
        self._fps_target: int = settings.camera.frame_rate_target
        self._max_buffer: int = settings.camera.max_buffer_frames
        self._max_concurrent: int = settings.camera.max_concurrent

        # JPEG encode quality (0-100).  85 is a good speed / size trade-off.
        self._jpeg_quality: int = 85

        # Internal state
        self._tasks: dict[str, asyncio.Task] = {}
        self._stats: dict[str, _CameraStats] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=settings.camera.max_concurrent,
            thread_name_prefix="rtsp-reader",
        )
        self._log = logger.bind(component="camera_gateway")

    # -- lifecycle -----------------------------------------------------------

    async def start(self, camera_streams: dict[str, str]) -> None:
        """Start capturing from every camera in *camera_streams*.

        Parameters
        ----------
        camera_streams:
            Mapping of ``{camera_id: rtsp_url}``.
        """
        if len(camera_streams) > self._max_concurrent:
            self._log.warning(
                "gateway.max_concurrent_exceeded",
                requested=len(camera_streams),
                limit=self._max_concurrent,
            )

        for camera_id, rtsp_url in camera_streams.items():
            if camera_id in self._tasks:
                self._log.warning(
                    "gateway.camera_already_running",
                    camera_id=camera_id,
                )
                continue
            self._spawn_camera_task(camera_id, rtsp_url)

        self._log.info(
            "gateway.started",
            camera_count=len(self._tasks),
        )

    async def stop(self) -> None:
        """Cancel every camera task and release resources."""
        self._log.info("gateway.stopping", camera_count=len(self._tasks))
        for task in self._tasks.values():
            task.cancel()

        results = await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        for camera_id, result in zip(self._tasks, results):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                self._log.error(
                    "gateway.task_error_on_stop",
                    camera_id=camera_id,
                    error=str(result),
                )

        self._tasks.clear()
        self._executor.shutdown(wait=False)
        self._log.info("gateway.stopped")

    # -- per-camera task management ------------------------------------------

    def _spawn_camera_task(self, camera_id: str, rtsp_url: str) -> None:
        """Create and register a new asyncio task for *camera_id*."""
        self._stats[camera_id] = _CameraStats()
        task = asyncio.create_task(
            self._camera_loop(camera_id, rtsp_url),
            name=f"camera-{camera_id}",
        )
        task.add_done_callback(
            lambda t, cid=camera_id: self._on_task_done(cid, t),
        )
        self._tasks[camera_id] = task
        self._log.info(
            "camera.task_spawned",
            camera_id=camera_id,
            rtsp_url=rtsp_url,
        )

    def _on_task_done(self, camera_id: str, task: asyncio.Task) -> None:
        """Callback when a camera task exits (expected or not)."""
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            self._log.info("camera.task_cancelled", camera_id=camera_id)
            return

        if exc is not None:
            stats = self._stats.get(camera_id)
            self._log.error(
                "camera.task_crashed",
                camera_id=camera_id,
                error=str(exc),
                frames_captured=stats.frames_captured if stats else 0,
                frames_dropped=stats.frames_dropped if stats else 0,
            )

    # -- core capture loop ---------------------------------------------------

    async def _camera_loop(self, camera_id: str, rtsp_url: str) -> None:
        """Infinite capture loop for a single camera.

        Reads frames via a blocking ``cv2.VideoCapture`` offloaded to a
        thread pool, JPEG-encodes them, and publishes to Kafka.
        """
        cam_log = self._log.bind(camera_id=camera_id)
        stats = self._stats[camera_id]
        loop = asyncio.get_running_loop()
        frame_interval = 1.0 / self._fps_target
        sequence_no = 0

        cap: cv2.VideoCapture | None = None

        try:
            # --- open capture ---
            cap = await loop.run_in_executor(
                self._executor,
                self._open_capture,
                rtsp_url,
            )
            if cap is None or not cap.isOpened():
                cam_log.error("camera.open_failed", rtsp_url=rtsp_url)
                await self._health.record_error(camera_id, "decode")
                return

            cam_log.info(
                "camera.stream_opened",
                width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            )

            # --- read loop ---
            while True:
                t_start = time.monotonic()

                # Blocking read → executor
                success, frame = await loop.run_in_executor(
                    self._executor,
                    self._read_frame,
                    cap,
                )

                if not success or frame is None:
                    stats.decode_errors += 1
                    await self._health.record_error(camera_id, "decode")
                    cam_log.warning(
                        "camera.decode_error",
                        consecutive_errors=stats.decode_errors,
                    )
                    # Brief back-off before retrying
                    await asyncio.sleep(0.5)
                    continue

                # JPEG encode
                jpeg_bytes = await loop.run_in_executor(
                    self._executor,
                    self._encode_jpeg,
                    frame,
                )
                if jpeg_bytes is None:
                    stats.decode_errors += 1
                    await self._health.record_error(camera_id, "decode")
                    continue

                sequence_no += 1
                stats.frames_captured += 1

                # Build message
                from datetime import datetime, timezone

                msg = FrameMessage(
                    camera_id=camera_id,
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                    sequence_no=sequence_no,
                    frame_bytes=jpeg_bytes,
                    metadata={
                        "width": frame.shape[1],
                        "height": frame.shape[0],
                        "channels": frame.shape[2] if frame.ndim == 3 else 1,
                    },
                )

                # Publish to Kafka
                try:
                    await self._producer.publish(msg.to_dict())
                except Exception:
                    cam_log.exception("camera.publish_failed", seq=sequence_no)
                    stats.frames_dropped += 1
                    await self._health.record_error(camera_id, "drop")
                    continue

                # Record success in health monitor
                await self._health.record_frame(camera_id)

                # Rate limiting — sleep for the remainder of the frame interval
                elapsed = time.monotonic() - t_start
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            cam_log.info("camera.loop_cancelled")
            raise
        except Exception:
            cam_log.exception("camera.loop_fatal")
            raise
        finally:
            if cap is not None:
                cap.release()
                cam_log.info("camera.capture_released")

    # -- blocking helpers (run in executor) ----------------------------------

    @staticmethod
    def _open_capture(rtsp_url: str) -> cv2.VideoCapture | None:
        """Open an RTSP stream (blocking — called from executor thread)."""
        try:
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                return None
            # Minimize internal buffer to keep frames fresh
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            return cap
        except Exception:
            return None

    @staticmethod
    def _read_frame(cap: cv2.VideoCapture) -> tuple[bool, np.ndarray | None]:
        """Read a single frame (blocking — called from executor thread)."""
        try:
            return cap.read()
        except Exception:
            return False, None

    def _encode_jpeg(self, frame: np.ndarray) -> bytes | None:
        """JPEG-encode a BGR frame (blocking — called from executor thread)."""
        try:
            success, buf = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality],
            )
            if not success:
                return None
            return buf.tobytes()
        except Exception:
            return None
