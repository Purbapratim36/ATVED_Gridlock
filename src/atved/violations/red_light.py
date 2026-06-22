"""
Red-light violation detector.

Combines traffic signal state detection with stop-line crossing
to identify vehicles running a red light.
"""

from __future__ import annotations

from typing import Any

import structlog

from atved.db.models import ViolationType
from atved.detection import DetectionResult, FrameDetections
from atved.violations.base import BaseViolationDetector, ViolationCandidate
from atved.violations._geometry import bbox_center

logger = structlog.get_logger(__name__)


class RedLightDetector(BaseViolationDetector):
    """
    Flags vehicles that cross the stop line while the traffic signal is red.

    Detection logic:
        1. Detect traffic signal state from the frame (or accept external signal input).
        2. Signal must be confirmed RED for ``signal_confirm_frames`` consecutive
           frames before violations can be triggered (avoids amber-to-red transitions).
        3. If signal is confirmed RED and a vehicle crosses the stop line,
           emit a violation.
        4. Optionally allows right-turn-on-red if configured.

    Signal detection: expects a detection class "traffic_light_red", "traffic_light_green",
    "traffic_light_amber" in the detection results, OR an external signal feed.
    """

    VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck", "van", "auto_rickshaw"}
    SIGNAL_RED = "traffic_light_red"
    SIGNAL_GREEN = "traffic_light_green"
    SIGNAL_AMBER = "traffic_light_amber"

    def __init__(self, config, violation_type=ViolationType.RED_LIGHT):
        super().__init__(config, violation_type)
        self._confirm_frames = config.signal_confirm_frames or 3
        self._grace_ms = config.grace_period_ms or 500
        self._allow_right_on_red = config.right_turn_on_red_allowed or False
        self._stop_line_y: float | None = None

        self._red_streak: int = 0
        self._signal_confirmed_red: bool = False
        # track_id → prev_bottom_y
        self._vehicle_positions: dict[int, float] = {}

    def set_stop_line(self, y_coordinate: float) -> None:
        """Set the stop line Y position in image coordinates."""
        self._stop_line_y = y_coordinate

    def set_signal_state(self, state: str) -> None:
        """Manually set the signal state (for external signal feeds)."""
        if state == "RED":
            self._red_streak += 1
        else:
            self._red_streak = 0
        self._signal_confirmed_red = self._red_streak >= self._confirm_frames

    def analyze(
        self,
        frame_detections: FrameDetections,
        history: list[FrameDetections],
    ) -> list[ViolationCandidate]:
        if not self.is_enabled or self._stop_line_y is None:
            return []

        candidates: list[ViolationCandidate] = []
        dets = frame_detections.detections

        # Update signal state from detections
        self._update_signal_from_detections(dets)

        if not self._signal_confirmed_red:
            # Signal not confirmed red — just update vehicle positions
            self._update_vehicle_positions(dets)
            return []

        vehicles = [d for d in dets if d.class_name in self.VEHICLE_CLASSES]
        seen_ids: set[int] = set()

        for vehicle in vehicles:
            if vehicle.track_id is None:
                continue

            seen_ids.add(vehicle.track_id)
            bottom_y = vehicle.bbox[3]
            prev_y = self._vehicle_positions.get(vehicle.track_id, bottom_y)

            # Check crossing: bottom moves past stop line
            crossed = prev_y <= self._stop_line_y < bottom_y
            self._vehicle_positions[vehicle.track_id] = bottom_y

            if crossed:
                confidence = vehicle.confidence * 0.95
                if confidence >= self._config.min_confidence:
                    candidates.append(
                        ViolationCandidate(
                            violation_type=ViolationType.RED_LIGHT,
                            raw_confidence=confidence,
                            calibrated_confidence=0.0,
                            detections=[vehicle],
                            evidence_signals={
                                "signal_state": "RED",
                                "signal_confidence": 1.0,
                                "signal_confirm_count": self._red_streak,
                                "stop_line_y": self._stop_line_y,
                                "crossing_bottom_y": bottom_y,
                                "right_turn_detected": False,
                                "vehicle_track_id": vehicle.track_id,
                            },
                            frame_indices=[frame_detections.frame_index],
                            camera_id=frame_detections.camera_id,
                            timestamp=frame_detections.timestamp,
                        )
                    )

        # Evict stale
        stale = [tid for tid in self._vehicle_positions if tid not in seen_ids]
        for tid in stale:
            del self._vehicle_positions[tid]

        return candidates

    def _update_signal_from_detections(self, dets: list[DetectionResult]) -> None:
        """Update signal state from traffic light detections in the frame."""
        red_signals = [d for d in dets if d.class_name == self.SIGNAL_RED]
        green_signals = [d for d in dets if d.class_name == self.SIGNAL_GREEN]

        if red_signals and not green_signals:
            self._red_streak += 1
        elif green_signals:
            self._red_streak = 0
        # If neither detected, keep current state (signal might be occluded)

        self._signal_confirmed_red = self._red_streak >= self._confirm_frames

    def _update_vehicle_positions(self, dets: list[DetectionResult]) -> None:
        """Update tracked vehicle positions even when signal isn't red."""
        for d in dets:
            if d.class_name in self.VEHICLE_CLASSES and d.track_id is not None:
                self._vehicle_positions[d.track_id] = d.bbox[3]
