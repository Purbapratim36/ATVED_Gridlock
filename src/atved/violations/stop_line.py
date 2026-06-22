"""
Stop-line violation detector.

Detects vehicles that cross the stop line when they should be stopped.
Requires per-camera stop-line coordinates in camera config.
"""

from __future__ import annotations

from typing import Any

import structlog

from atved.db.models import ViolationType
from atved.detection import DetectionResult, FrameDetections
from atved.violations.base import BaseViolationDetector, ViolationCandidate
from atved.violations._geometry import bbox_center

logger = structlog.get_logger(__name__)


class StopLineDetector(BaseViolationDetector):
    """
    Flags vehicles crossing a stop line.

    Detection logic:
        1. The stop line is defined as a horizontal Y-coordinate in the
           camera's image space (from ``camera.config_json.stop_line_y``).
        2. Track the vehicle's bottom-center point across frames.
        3. If the bottom-center crosses from above to below the stop line,
           record the crossing event.
        4. A grace period prevents false positives during legitimate
           creep-forward at signals.

    This detector is usually paired with the red-light detector — a stop-line
    crossing is only a violation when the signal is red. When used standalone,
    it flags all crossings for manual review.
    """

    VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck", "van", "auto_rickshaw"}

    def __init__(self, config, violation_type=ViolationType.STOP_LINE):
        super().__init__(config, violation_type)
        self._grace_ms = config.grace_period_ms or 500
        self._stop_line_y: float | None = None
        # track_id → {"prev_y": float, "crossed_at_ms": float | None}
        self._tracking: dict[int, dict[str, Any]] = {}

    def set_stop_line(self, y_coordinate: float) -> None:
        """Set the stop line Y position in image coordinates."""
        self._stop_line_y = y_coordinate

    def analyze(
        self,
        frame_detections: FrameDetections,
        history: list[FrameDetections],
    ) -> list[ViolationCandidate]:
        if not self.is_enabled or self._stop_line_y is None:
            return []

        candidates: list[ViolationCandidate] = []
        dets = frame_detections.detections
        now_ms = frame_detections.timestamp.timestamp() * 1000

        vehicles = [d for d in dets if d.class_name in self.VEHICLE_CLASSES]
        seen_ids: set[int] = set()

        for vehicle in vehicles:
            if vehicle.track_id is None:
                continue

            seen_ids.add(vehicle.track_id)
            # Bottom-center of vehicle bbox
            bottom_y = vehicle.bbox[3]
            _, center_x = bbox_center(vehicle.bbox)[0], bbox_center(vehicle.bbox)[0]

            state = self._tracking.setdefault(
                vehicle.track_id, {"prev_y": bottom_y, "crossed_at_ms": None}
            )
            prev_y = state["prev_y"]

            # Detect crossing: vehicle bottom moves from above to below stop line
            crossed_now = prev_y <= self._stop_line_y < bottom_y
            state["prev_y"] = bottom_y

            if crossed_now and state["crossed_at_ms"] is None:
                state["crossed_at_ms"] = now_ms

            if state["crossed_at_ms"] is not None:
                elapsed = now_ms - state["crossed_at_ms"]
                if elapsed >= self._grace_ms:
                    crossing_speed = self._estimate_speed(vehicle, state)
                    confidence = vehicle.confidence * 0.9
                    if confidence >= self._config.min_confidence:
                        candidates.append(
                            ViolationCandidate(
                                violation_type=ViolationType.STOP_LINE,
                                raw_confidence=confidence,
                                calibrated_confidence=0.0,
                                detections=[vehicle],
                                evidence_signals={
                                    "stop_line_y": self._stop_line_y,
                                    "vehicle_bottom_y": bottom_y,
                                    "crossing_speed_estimate": round(crossing_speed, 2),
                                    "grace_period_elapsed_ms": round(elapsed, 0),
                                    "vehicle_track_id": vehicle.track_id,
                                },
                                frame_indices=[frame_detections.frame_index],
                                camera_id=frame_detections.camera_id,
                                timestamp=frame_detections.timestamp,
                            )
                        )
                    # Reset so we don't re-emit for same crossing
                    state["crossed_at_ms"] = None

        # Evict stale tracks
        stale = [tid for tid in self._tracking if tid not in seen_ids]
        for tid in stale:
            del self._tracking[tid]

        return candidates

    def _estimate_speed(self, vehicle: DetectionResult, state: dict) -> float:
        """Rough speed estimate from bbox displacement (pixels/frame)."""
        return abs(vehicle.bbox[3] - state.get("prev_y", vehicle.bbox[3]))
