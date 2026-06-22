"""
Helmet violation detector.

Detects motorcycle riders not wearing helmets by finding spatially
associated motorcycle-rider pairs and checking for helmet presence
in the rider's head region across consecutive frames.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from atved.db.models import ViolationType
from atved.detection import DetectionResult, FrameDetections
from atved.violations.base import BaseViolationDetector, ViolationCandidate
from atved.violations._geometry import compute_iou, vertical_overlap_ratio

logger = structlog.get_logger(__name__)


class HelmetViolationDetector(BaseViolationDetector):
    """
    Flags riders on motorcycles who are not wearing helmets.

    Detection logic:
        1. Find all motorcycles in the frame.
        2. For each motorcycle, find spatially associated riders
           (rider bbox overlaps motorcycle bbox vertically by ≥50%).
        3. For each rider, extract the head region (upper 35% of rider bbox).
        4. Check if any "helmet" class detection overlaps the head region.
        5. If no helmet is found for ``min_consecutive_frames`` consecutive
           frames (using track_id continuity), emit a violation candidate.

    This approach avoids false positives from momentary occlusion (a rider
    turning their head, another vehicle briefly blocking the view) by
    requiring sustained absence of helmet across multiple frames.
    """

    MOTORCYCLE_CLASSES = {"motorcycle", "bike"}
    RIDER_CLASSES = {"rider", "driver", "person"}
    HELMET_CLASS = "helmet"
    NO_HELMET_CLASS = "no helmet" # Handle specialized model classes
    HEAD_REGION_RATIO = 0.35  # upper 35% of rider bbox is the head region

    def __init__(self, config, violation_type=ViolationType.HELMET):
        super().__init__(config, violation_type)
        self._no_helmet_streak: dict[int, int] = {}  # track_id → consecutive count

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
        helmets = [d for d in dets if d.class_name == self.HELMET_CLASS or d.class_name == "With Helmet"]
        no_helmets = [d for d in dets if d.class_name == self.NO_HELMET_CLASS or d.class_name == "Without Helmet"]

        # Track IDs observed this frame — used to decay stale streaks
        seen_track_ids: set[int] = set()

        for moto in motorcycles:
            associated_riders = self._find_associated_riders(moto, riders)

            for rider in associated_riders:
                if rider.track_id is None:
                    continue

                seen_track_ids.add(rider.track_id)
                head_region = self._extract_head_region(rider)
                has_helmet = self._check_helmet_in_region(head_region, helmets)
                has_no_helmet_box = self._check_helmet_in_region(head_region, no_helmets)

                if has_helmet:
                    # Reset streak — rider is wearing helmet
                    self._no_helmet_streak.pop(rider.track_id, None)
                    continue
                    
                if has_no_helmet_box:
                    # Specialized model explicitly detected 'no helmet', count it immediately
                    pass

                # No helmet detected — increment streak
                streak = self._no_helmet_streak.get(rider.track_id, 0) + 1
                self._no_helmet_streak[rider.track_id] = streak

                min_frames = self._config.min_consecutive_frames
                if streak >= min_frames:
                    confidence = self._compute_confidence(rider, moto, streak)
                    if confidence >= self._config.min_confidence:
                        candidates.append(
                            ViolationCandidate(
                                violation_type=ViolationType.HELMET,
                                raw_confidence=confidence,
                                calibrated_confidence=0.0,
                                detections=[moto, rider],
                                evidence_signals={
                                    "rider_track_id": rider.track_id,
                                    "motorcycle_track_id": moto.track_id,
                                    "consecutive_no_helmet_frames": streak,
                                    "helmet_detected": False,
                                    "rider_confidence": rider.confidence,
                                    "motorcycle_confidence": moto.confidence,
                                },
                                frame_indices=[frame_detections.frame_index],
                                camera_id=frame_detections.camera_id,
                                timestamp=frame_detections.timestamp,
                            )
                        )

        # Decay streaks for riders no longer visible
        stale = [tid for tid in self._no_helmet_streak if tid not in seen_track_ids]
        for tid in stale:
            self._no_helmet_streak[tid] = max(0, self._no_helmet_streak[tid] - 1)
            if self._no_helmet_streak[tid] == 0:
                del self._no_helmet_streak[tid]

        return candidates

    # ── Helpers ──────────────────────────────────────────────────────

    def _find_associated_riders(
        self,
        motorcycle: DetectionResult,
        riders: list[DetectionResult],
    ) -> list[DetectionResult]:
        """Find riders whose bbox vertically overlaps the motorcycle by ≥50%."""
        associated = []
        for rider in riders:
            v_overlap = vertical_overlap_ratio(motorcycle.bbox, rider.bbox)
            iou = compute_iou(motorcycle.bbox, rider.bbox)
            # Rider should be above/on the motorcycle with significant overlap
            if v_overlap >= 0.5 or iou >= 0.15:
                associated.append(rider)
        return associated

    def _extract_head_region(
        self, rider: DetectionResult
    ) -> tuple[float, float, float, float]:
        """Return the upper portion of the rider bbox as the head region."""
        x1, y1, x2, y2 = rider.bbox
        head_height = (y2 - y1) * self.HEAD_REGION_RATIO
        return (x1, y1, x2, y1 + head_height)

    def _check_helmet_in_region(
        self,
        head_region: tuple[float, float, float, float],
        helmets: list[DetectionResult],
    ) -> bool:
        """Check if any helmet detection overlaps the head region."""
        for helmet in helmets:
            iou = compute_iou(head_region, helmet.bbox)
            if iou >= 0.2:  # Loose threshold — helmet just needs to be in head area
                return True
        return False

    def _compute_confidence(
        self,
        rider: DetectionResult,
        motorcycle: DetectionResult,
        streak: int,
    ) -> float:
        """
        Combine detection confidences with streak length for overall score.

        Longer streaks increase confidence (sustained observation is stronger
        evidence than a single frame).
        """
        base = min(rider.confidence, motorcycle.confidence)
        streak_bonus = min(0.15, 0.03 * (streak - self._config.min_consecutive_frames))
        return min(1.0, base + streak_bonus)
