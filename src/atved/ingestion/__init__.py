"""
Ingestion layer for ATVED.

Manages multi-camera RTSP stream capture, Kafka frame publishing,
and per-camera health monitoring backed by Redis.
"""

from atved.ingestion.gateway import CameraGateway, FrameMessage
from atved.ingestion.health_monitor import CameraHealthMonitor
from atved.ingestion.kafka_producer import KafkaFrameProducer

__all__ = [
    "CameraGateway",
    "CameraHealthMonitor",
    "FrameMessage",
    "KafkaFrameProducer",
]
