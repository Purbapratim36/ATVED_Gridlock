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
    CONFIRMATION_THRESHOLD = 8

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

        # Track available helmets to prevent one helmet from "protecting" multiple riders
        available_helmets = helmets.copy()
        available_no_helmets = no_helmets.copy()

        for moto in motorcycles:
            associated_riders = self._find_associated_riders(moto, riders)

            for rider in associated_riders:
                if rider.track_id is None:
                    continue

                seen_track_ids.add(rider.track_id)
                head_region = self._extract_head_region(rider)
                
                has_helmet = self._check_and_consume_helmet(head_region, available_helmets)
                has_no_helmet_box = self._check_and_consume_helmet(head_region, available_no_helmets)

                if has_helmet:
                    # Decay streak — rider is wearing helmet
                    current_streak = self._no_helmet_streak.get(rider.track_id, 0)
                    self._no_helmet_streak[rider.track_id] = max(0, current_streak - 2)
                    continue
                    
                if has_no_helmet_box:
                    # Specialized model explicitly detected 'no helmet', count it immediately
                    pass

                # No helmet detected — increment streak
                streak = self._no_helmet_streak.get(rider.track_id, 0) + 1
                self._no_helmet_streak[rider.track_id] = streak

                # Use the dynamic threshold from config (defaulting to 8 if not set)
                threshold = getattr(self._config, 'min_consecutive_frames', 8)

                if streak >= threshold:
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
                        # Reset after emission
                        self._no_helmet_streak[rider.track_id] = 0

        # Decay streaks for riders no longer visible
        stale = [tid for tid in self._no_helmet_streak if tid not in seen_track_ids]
        for tid in stale:
            self._no_helmet_streak[tid] = max(0, self._no_helmet_streak[tid] - 2)
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

    def _check_and_consume_helmet(
        self,
        head_region: tuple[float, float, float, float],
        available_helmets: list[DetectionResult],
    ) -> bool:
        """
        Check if any helmet overlaps the head region. 
        If found, it 'consumes' the best matching helmet from the list 
        so it cannot be used by another rider (fixing double-counting for pillions).
        """
        best_iou = 0
        best_idx = -1
        
        for i, helmet in enumerate(available_helmets):
            iou = compute_iou(head_region, helmet.bbox)
            if iou >= 0.2 and iou > best_iou:
                best_iou = iou
                best_idx = i
                
        if best_idx != -1:
            available_helmets.pop(best_idx)
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
