"""
Evidence generator — assembles annotated frames, metadata, and
hash-sealed evidence records for human review.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np
import structlog
from prometheus_client import Counter, Histogram

from atved.core.evidence import EvidenceSealer, SealedEvidence
from atved.detection import DetectionResult
from atved.evidence.face_blur import FaceBlur
from atved.violations.base import ViolationCandidate

logger = structlog.get_logger(__name__)

EVIDENCE_GENERATED = Counter("atved_evidence_generated_total", "Evidence records generated")
EVIDENCE_LATENCY = Histogram(
    "atved_evidence_generation_seconds", "Evidence generation latency",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
)

# Annotation drawing constants
_COLORS = {
    "car": (0, 255, 0),
    "motorcycle": (255, 165, 0),
    "bus": (0, 0, 255),
    "truck": (128, 0, 128),
    "rider": (255, 255, 0),
    "driver": (0, 255, 255),
    "pedestrian": (255, 0, 255),
    "default": (0, 200, 0),
}


class EvidenceGenerator:
    """
    Assembles legally defensible evidence records from violation
    candidates, raw frames, and plate results.

    Pipeline:
        1. Draw bounding boxes and labels on evidence frames.
        2. Blur incidental faces (privacy protection).
        3. Encode annotated frames as JPEG.
        4. Hash-seal with metadata for chain of custody.
    """

    def __init__(
        self,
        sealer: EvidenceSealer,
        face_blur: FaceBlur,
        model_version: str = "0.1.0",
        jpeg_quality: int = 95,
    ) -> None:
        self._sealer = sealer
        self._face_blur = face_blur
        self._model_version = model_version
        self._jpeg_quality = jpeg_quality

    @EVIDENCE_LATENCY.time()
    def generate(
        self,
        candidate: ViolationCandidate,
        frames: list[np.ndarray],
        plate_text: str | None = None,
        plate_confidence: float | None = None,
        plate_bbox: tuple[float, float, float, float] | None = None,
        camera_config: dict[str, Any] | None = None,
        previous_hash: str | None = None,
    ) -> SealedEvidence:
        """
        Generate a sealed evidence record.

        Parameters
        ----------
        candidate:
            The violation candidate with detection data.
        frames:
            Raw BGR frames associated with this violation.
        plate_text:
            Recognised plate text (if available).
        plate_confidence:
            OCR confidence for the plate.
        plate_bbox:
            Plate bounding box in frame coordinates.
        camera_config:
            Camera configuration snapshot for reproducibility.
        previous_hash:
            Hash of the previous evidence record for chain linking.
        """
        annotated_frames: list[bytes] = []
        frame_metadata: list[dict[str, Any]] = []

        for i, frame in enumerate(frames):
            # Draw annotations
            annotated = self._annotate_frame(
                frame.copy(), candidate.detections, plate_bbox
            )
            # Blur faces (privacy)
            annotated = self._face_blur.blur_faces(annotated)
            # Encode to JPEG
            _, jpeg_bytes = cv2.imencode(
                ".jpg", annotated,
                [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality],
            )
            annotated_frames.append(jpeg_bytes.tobytes())
            frame_metadata.append({
                "frame_index": i,
                "timestamp": candidate.timestamp.isoformat(),
                "camera_id": candidate.camera_id,
            })

        # Build metadata
        metadata = {
            "violation_type": candidate.violation_type.value,
            "camera_id": candidate.camera_id,
            "detected_at": candidate.timestamp.isoformat(),
            "raw_confidence": round(candidate.raw_confidence, 4),
            "calibrated_confidence": round(candidate.calibrated_confidence, 4),
            "vehicle_type": self._get_vehicle_type(candidate.detections),
            "plate_text": plate_text,
            "plate_confidence": round(plate_confidence, 4) if plate_confidence else None,
            "model_version": self._model_version,
            "evidence_signals": candidate.evidence_signals,
            "camera_config_snapshot": camera_config,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Build annotations JSON
        annotations = {
            "bounding_boxes": [
                {
                    "class": d.class_name,
                    "bbox": list(d.bbox),
                    "confidence": round(d.confidence, 4),
                    "track_id": d.track_id,
                }
                for d in candidate.detections
            ],
            "plate_bbox": list(plate_bbox) if plate_bbox else None,
            "trajectory": candidate.trajectory,
        }

        sealed = self._sealer.seal(
            metadata=metadata,
            annotations=annotations,
            frames=annotated_frames,
            frame_metadata=frame_metadata,
            previous_hash=previous_hash,
        )

        EVIDENCE_GENERATED.inc()
        return sealed

    def _annotate_frame(
        self,
        frame: np.ndarray,
        detections: list[DetectionResult],
        plate_bbox: tuple[float, float, float, float] | None = None,
    ) -> np.ndarray:
        """Draw bounding boxes and labels on a frame."""
        for det in detections:
            x1, y1, x2, y2 = [int(v) for v in det.bbox]
            color = _COLORS.get(det.class_name, _COLORS["default"])

            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"{det.class_name} {det.confidence:.2f}"
            if det.track_id is not None:
                label += f" T{det.track_id}"

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw, y1), color, -1)
            cv2.putText(
                frame, label, (x1, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
            )

        if plate_bbox:
            px1, py1, px2, py2 = [int(v) for v in plate_bbox]
            cv2.rectangle(frame, (px1, py1), (px2, py2), (0, 255, 255), 2)

        return frame

    @staticmethod
    def _get_vehicle_type(detections: list[DetectionResult]) -> str:
        """Extract the primary vehicle type from detections."""
        vehicle_classes = {"car", "motorcycle", "bus", "truck", "van", "auto_rickshaw", "bicycle"}
        for d in detections:
            if d.class_name in vehicle_classes:
                return d.class_name
        return "unknown"
