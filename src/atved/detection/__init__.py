"""
Detection & tracking engine for ATVED.

Provides YOLOv8-based object detection, ByteTrack multi-object tracking,
and a GPU batch-inference orchestrator for real-time traffic analysis.

Public API
----------
- :class:`DetectionResult` — Single bounding-box detection.
- :class:`FrameDetections`  — All detections for one video frame.
- :class:`Detector`         — YOLOv8 inference wrapper.
- :class:`ObjectTracker`    — Per-camera ByteTrack tracker pool.
- :class:`BatchInferenceEngine` — Orchestrates preprocess → detect → track.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

__all__ = [
    "DetectionResult",
    "FrameDetections",
    "Detector",
    "ObjectTracker",
    "BatchInferenceEngine",
]


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DetectionResult:
    """A single object detection in original-image coordinates.

    Attributes
    ----------
    bbox:
        Bounding box as ``(x1, y1, x2, y2)`` in **original** image pixels.
    class_name:
        Human-readable class label (e.g. ``"car"``).
    class_id:
        Integer class index matching the model's output order.
    confidence:
        Detection confidence score in ``[0, 1]``.
    track_id:
        Assigned by :class:`ObjectTracker`; ``None`` before tracking.
    """

    bbox: tuple[float, float, float, float]
    class_name: str
    class_id: int
    confidence: float
    track_id: int | None = None


@dataclass(slots=True)
class FrameDetections:
    """Container for all detections produced from a single video frame.

    Attributes
    ----------
    frame_index:
        Monotonically increasing frame counter (per camera).
    camera_id:
        Unique identifier of the originating camera stream.
    timestamp:
        Wall-clock time when the frame was captured (UTC preferred).
    detections:
        Ordered list of :class:`DetectionResult` instances.
    inference_time_ms:
        End-to-end inference latency for this frame (milliseconds).
    """

    frame_index: int
    camera_id: str
    timestamp: datetime
    detections: list[DetectionResult] = field(default_factory=list)
    inference_time_ms: float = 0.0


# ---------------------------------------------------------------------------
# Lazy imports — avoid importing heavy dependencies at package import time
# ---------------------------------------------------------------------------

def __getattr__(name: str):  # noqa: N807
    """Lazily import heavyweight classes on first access."""
    if name == "Detector":
        from atved.detection.detector import Detector
        return Detector
    if name == "ObjectTracker":
        from atved.detection.tracker import ObjectTracker
        return ObjectTracker
    if name == "BatchInferenceEngine":
        from atved.detection.batch_engine import BatchInferenceEngine
        return BatchInferenceEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
