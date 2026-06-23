"""
Triple riding violation detector.

Flags motorcycles carrying more than the allowed number of riders
(default threshold: 2). Uses strict spatial association.
"""

from __future__ import annotations

from typing import Any

import structlog

from atved.db.models import ViolationType
from atved.detection import DetectionResult, FrameDetections
from atved.violations.base import BaseViolationDetector, ViolationCandidate
from atved.violations._geometry import compute_iou, bbox_center

logger = structlog.get_logger(__name__)


class TripleRidingDetector(BaseViolationDetector):
    MOTORCYCLE_CLASSES = {"motorcycle"}
    RIDER_CLASSES = {"rider", "driver"}  # Removed "person" to avoid pedestrians
    CONFIRMATION_THRESHOLD = 5

    def __init__(self, config, violation_type=ViolationType.TRIPLE_RIDING):
        super().__init__(config, violation_type)
        self._max_riders = config.max_riders_threshold or 2
        self._overload_streak: dict[int, int] = {}  # moto_track_id → streak

    def analyze(
        self,
        frame_detections: FrameDetections,
        history: list[FrameDetections],
    ) -> list[ViolationCandidate]:
        if not self.is_enabled:
            return []

        candidates: list[ViolationCandidate] = []
        dets = frame_detections.detections

        motorcycles = [d for d in dets if d.class_name in self.MOTORCYCLE_CLASSES]
        riders = [d for d in dets if d.class_name in self.RIDER_CLASSES]

        seen_moto_ids: set[int] = set()

        for moto in motorcycles:
            if moto.track_id is None:
                continue

            seen_moto_ids.add(moto.track_id)

            associated = self._count_riders(moto, riders)
            rider_count = len(associated)

            if rider_count > self._max_riders:
                streak = self._overload_streak.get(moto.track_id, 0) + 1
                self._overload_streak[moto.track_id] = streak

                if streak >= self.CONFIRMATION_THRESHOLD:
                    confidence = self._compute_confidence(moto, associated, rider_count)
                    if confidence >= self._config.min_confidence:
                        candidates.append(
                            ViolationCandidate(
                                violation_type=ViolationType.TRIPLE_RIDING,
                                raw_confidence=confidence,
                                calibrated_confidence=0.0,
                                detections=[moto, *associated],
                                evidence_signals={
                                    "rider_count": rider_count,
                                    "max_allowed": self._max_riders,
                                    "motorcycle_track_id": moto.track_id,
                                    "rider_track_ids": [r.track_id for r in associated if r.track_id is not None],
                                    "consecutive_overloaded_frames": streak,
                                    "average_rider_count": float(rider_count),
                                },
                                frame_indices=[frame_detections.frame_index],
                                camera_id=frame_detections.camera_id,
                                timestamp=frame_detections.timestamp,
                            )
                        )
                        # Reset streak after emission to avoid duplicate alerts
                        self._overload_streak[moto.track_id] = 0
            else:
                # Decay logic
                current_streak = self._overload_streak.get(moto.track_id, 0)
                self._overload_streak[moto.track_id] = max(0, current_streak - 2)

        # Clean up stale entries
        stale = [mid for mid in self._overload_streak if mid not in seen_moto_ids]
        for mid in stale:
            del self._overload_streak[mid]

        return candidates

    def _count_riders(
        self, motorcycle: DetectionResult, riders: list[DetectionResult]
    ) -> list[DetectionResult]:
        associated = []
        mx1, my1, mx2, my2 = motorcycle.bbox
        for rider in riders:
            rx1, ry1, rx2, ry2 = rider.bbox
            
            # Area > 1200
            area = (rx2 - rx1) * (ry2 - ry1)
            if area <= 1200:
                continue

            # Centroid inside motorcycle bbox
            cx, cy = bbox_center(rider.bbox)
            if not (mx1 <= cx <= mx2 and my1 <= cy <= my2):
                continue
                
            # IoU > 0.15
            iou = compute_iou(motorcycle.bbox, rider.bbox)
            if iou > 0.15:
                associated.append(rider)
                
        return associated

    def _compute_confidence(
        self,
        motorcycle: DetectionResult,
        riders: list[DetectionResult],
        avg_count: float,
    ) -> float:
        det_conf = min(
            motorcycle.confidence,
            min((r.confidence for r in riders), default=0.0),
        )
        excess_ratio = min((avg_count - self._max_riders) / self._max_riders, 1.0)
        return min(1.0, det_conf * (0.8 + 0.2 * excess_ratio))
