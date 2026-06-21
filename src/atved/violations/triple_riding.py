"""
Triple riding violation detector.

Flags motorcycles carrying more than the allowed number of riders
(default threshold: 2). Uses spatial association between motorcycle
and rider detections, stabilised across consecutive frames.
"""

from __future__ import annotations

from typing import Any

import structlog

from atved.db.models import ViolationType
from atved.detection import DetectionResult, FrameDetections
from atved.violations.base import BaseViolationDetector, ViolationCandidate
from atved.violations._geometry import compute_iou, vertical_overlap_ratio

logger = structlog.get_logger(__name__)


class TripleRidingDetector(BaseViolationDetector):
    """
    Detects motorcycles with more riders than allowed.

    Detection logic:
        1. Find all motorcycles in the frame.
        2. For each motorcycle, count spatially associated riders.
        3. If rider count exceeds ``max_riders_threshold`` for
           ``min_consecutive_frames``, emit a violation.
        4. Uses motorcycle track_id for temporal consistency.
    """

    MOTORCYCLE_CLASSES = {"motorcycle"}
    RIDER_CLASSES = {"rider", "driver"}

    def __init__(self, config, violation_type=ViolationType.TRIPLE_RIDING):
        super().__init__(config, violation_type)
        self._max_riders = config.max_riders_threshold or 2
        self._overload_streak: dict[int, list[int]] = {}  # moto_track_id → [rider_counts]

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

            # Record count in streak tracker
            streak = self._overload_streak.setdefault(moto.track_id, [])
            streak.append(rider_count)

            # Keep only recent history
            max_history = self._config.min_consecutive_frames + 5
            if len(streak) > max_history:
                streak[:] = streak[-max_history:]

            # Check if overloaded for enough consecutive frames
            min_frames = self._config.min_consecutive_frames
            if len(streak) >= min_frames:
                recent = streak[-min_frames:]
                if all(c > self._max_riders for c in recent):
                    avg_count = sum(recent) / len(recent)
                    confidence = self._compute_confidence(moto, associated, avg_count)

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
                                    "rider_track_ids": [r.track_id for r in associated],
                                    "consecutive_overloaded_frames": min_frames,
                                    "average_rider_count": round(avg_count, 1),
                                },
                                frame_indices=[frame_detections.frame_index],
                                camera_id=frame_detections.camera_id,
                                timestamp=frame_detections.timestamp,
                            )
                        )
                        # Reset streak after emission to avoid duplicate alerts
                        self._overload_streak[moto.track_id] = []

        # Clean up stale entries
        stale = [mid for mid in self._overload_streak if mid not in seen_moto_ids]
        for mid in stale:
            del self._overload_streak[mid]

        return candidates

    def _count_riders(
        self, motorcycle: DetectionResult, riders: list[DetectionResult]
    ) -> list[DetectionResult]:
        """Find riders spatially associated with this motorcycle."""
        associated = []
        for rider in riders:
            v_overlap = vertical_overlap_ratio(motorcycle.bbox, rider.bbox)
            iou = compute_iou(motorcycle.bbox, rider.bbox)
            if v_overlap >= 0.4 or iou >= 0.1:
                associated.append(rider)
        return associated

    def _compute_confidence(
        self,
        motorcycle: DetectionResult,
        riders: list[DetectionResult],
        avg_count: float,
    ) -> float:
        """Higher rider count and better detection confidence → higher score."""
        det_conf = min(
            motorcycle.confidence,
            min((r.confidence for r in riders), default=0.0),
        )
        excess_ratio = min((avg_count - self._max_riders) / self._max_riders, 1.0)
        return min(1.0, det_conf * (0.8 + 0.2 * excess_ratio))
