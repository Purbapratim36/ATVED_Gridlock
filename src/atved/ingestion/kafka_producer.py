"""
Kafka frame publisher for ATVED ingestion pipeline.

Wraps an ``AIOKafkaProducer`` to publish JPEG-encoded camera frames onto the
``camera-frames`` topic.  Provides:

* **orjson** serialization for minimal latency.
* **tenacity** retry logic on transient broker errors.
* **prometheus_client** metrics (published-frame counter + publish-latency
  histogram).
* Async-context-manager lifecycle (``async with KafkaFrameProducer(…)``).
"""

from __future__ import annotations

import base64
import time
from typing import TYPE_CHECKING

import orjson
import structlog
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
from prometheus_client import Counter, Histogram
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

if TYPE_CHECKING:
    from atved.config import Settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

FRAMES_PUBLISHED = Counter(
    "atved_ingestion_frames_published_total",
    "Total camera frames successfully published to Kafka.",
    ["camera_id"],
)

PUBLISH_LATENCY = Histogram(
    "atved_ingestion_publish_latency_seconds",
    "Latency for a single Kafka publish call.",
    ["camera_id"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

def _serialize_frame_message(msg: dict) -> bytes:
    """Encode a frame-message dict to compact JSON bytes via *orjson*."""
    return orjson.dumps(msg)


# ---------------------------------------------------------------------------
# Producer
# ---------------------------------------------------------------------------

class KafkaFrameProducer:
    """Async Kafka producer that publishes ``FrameMessage`` dicts.

    Usage::

        async with KafkaFrameProducer(settings) as producer:
            await producer.publish(frame_dict)

    Parameters
    ----------
    settings:
        The application-wide ``Settings`` instance.  Kafka bootstrap servers
        and topic name are read from ``settings.kafka``.
    """

    def __init__(self, settings: Settings) -> None:
        self._bootstrap_servers: str = settings.kafka.bootstrap_servers
        self._topic: str = settings.kafka.topics.frames
        self._producer: AIOKafkaProducer | None = None
        self._log = logger.bind(component="kafka_producer", topic=self._topic)

    # -- lifecycle -----------------------------------------------------------

    async def start(self) -> None:
        """Create and start the underlying ``AIOKafkaProducer``."""
        self._log.info("kafka_producer.starting", servers=self._bootstrap_servers)
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=_serialize_frame_message,
            key_serializer=lambda k: k.encode("utf-8") if isinstance(k, str) else k,
            # Durability: wait for the leader to acknowledge
            acks="all",
            # Linger briefly to batch small messages
            linger_ms=5,
            max_batch_size=1_048_576,  # 1 MiB per batch
            compression_type="gzip",
        )
        await self._producer.start()
        self._log.info("kafka_producer.started")

    async def stop(self) -> None:
        """Flush pending messages and close the producer."""
        if self._producer is not None:
            self._log.info("kafka_producer.stopping")
            await self._producer.stop()
            self._producer = None
            self._log.info("kafka_producer.stopped")

    async def __aenter__(self) -> KafkaFrameProducer:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # noqa: ANN001
        await self.stop()

    # -- publish -------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(KafkaError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=2),
        reraise=True,
    )
    async def publish(self, frame_msg: dict) -> None:
        """Publish a single frame message to Kafka.

        The ``camera_id`` field is used as the partition key so that frames
        from the same camera always land on the same partition (preserving
        temporal order per camera).

        Parameters
        ----------
        frame_msg:
            A dict matching the ``FrameMessage`` schema.  Must contain at
            least ``camera_id``.

        Raises
        ------
        KafkaError
            If the message cannot be delivered after retries.
        RuntimeError
            If the producer has not been started.
        """
        if self._producer is None:
            raise RuntimeError("KafkaFrameProducer is not started — call start() first.")

        camera_id: str = frame_msg["camera_id"]

        # Base64-encode raw bytes for JSON transport if still bytes
        payload = frame_msg.copy()
        if isinstance(payload.get("frame_bytes"), (bytes, bytearray)):
            payload["frame_bytes"] = base64.b64encode(payload["frame_bytes"]).decode("ascii")

        t0 = time.monotonic()
        await self._producer.send_and_wait(
            self._topic,
            value=payload,
            key=camera_id,
        )
        elapsed = time.monotonic() - t0

        PUBLISH_LATENCY.labels(camera_id=camera_id).observe(elapsed)
        FRAMES_PUBLISHED.labels(camera_id=camera_id).inc()

        self._log.debug(
            "frame.published",
            camera_id=camera_id,
            seq=frame_msg.get("sequence_no"),
            latency_ms=round(elapsed * 1000, 2),
        )
