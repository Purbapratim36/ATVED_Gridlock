"""
Wrong-side driving violation detector.

Identifies vehicles travelling in the wrong direction by comparing
their computed trajectory against the camera's expected direction.
"""

from __future__ import annotations

import math
import time
from typing import Any

import structlog

from atved.db.models import ViolationType
from atved.detection import DetectionResult, FrameDetections
from atved.violations.base import BaseViolationDetector, ViolationCandidate
from atved.violations._geometry import bbox_center

logger = structlog.get_logger(__name__)


class WrongSideDetector(BaseViolationDetector):
    """
    Flags vehicles driving against the expected traffic direction.

    Detection logic:
        1. Track vehicle centroid positions across frames.
        2. Compute direction of travel from trajectory (last N positions).
        3. Compare against expected direction for this camera lane.
        4. If deviation exceeds ``direction_deviation_degrees`` for longer
           than ``min_duration_seconds``, emit a violation.

    The expected direction is configured per-camera in ``camera.config_json``
    as ``expected_direction_deg`` (0 = right, 90 = down, 180 = left, 270 = up).
    """

    VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck", "van", "auto_rickshaw"}
    MIN_TRAJECTORY_POINTS = 5

    def __init__(self, config, violation_type=ViolationType.WRONG_SIDE):
        super().__init__(config, violation_type)
        self._deviation_threshold = config.direction_deviation_degrees or 135
        self._min_duration = config.min_duration_seconds or 2.0
        # track_id → list of (timestamp, centroid_x, centroid_y)
        self._trajectories: dict[int, list[tuple[float, float, float]]] = {}
        self._expected_direction: float | None = None

    def set_expected_direction(self, degrees: float) -> None:
        """Set the expected traffic direction for this camera (0-360 degrees)."""
        self._expected_direction = degrees % 360

    def analyze(
        self,
        frame_detections: FrameDetections,
        history: list[FrameDetections],
    ) -> list[ViolationCandidate]:
        if not self.is_enabled or self._expected_direction is None:
            return []

        candidates: list[ViolationCandidate] = []
        dets = frame_detections.detections
        now = frame_detections.timestamp.timestamp()

        vehicles = [d for d in dets if d.class_name in self.VEHICLE_CLASSES]
        seen_ids: set[int] = set()

        for vehicle in vehicles:
            if vehicle.track_id is None:
                continue

            seen_ids.add(vehicle.track_id)
            cx, cy = bbox_center(vehicle.bbox)

            traj = self._trajectories.setdefault(vehicle.track_id, [])
            traj.append((now, cx, cy))

            # Keep trajectory bounded (last 60 data points)
            if len(traj) > 60:
                traj[:] = traj[-60:]

            if len(traj) < self.MIN_TRAJECTORY_POINTS:
                continue

            travel_dir = self._compute_direction(traj)
            if travel_dir is None:
                continue

            deviation = self._angle_difference(travel_dir, self._expected_direction)
            duration = traj[-1][0] - traj[0][0]

            if deviation >= self._deviation_threshold and duration >= self._min_duration:
                confidence = self._compute_confidence(vehicle, deviation, duration)
                if confidence >= self._config.min_confidence:
                    trajectory_points = [(t[1], t[2]) for t in traj]
                    candidates.append(
                        ViolationCandidate(
                            violation_type=ViolationType.WRONG_SIDE,
                            raw_confidence=confidence,
                            calibrated_confidence=0.0,
                            detections=[vehicle],
                            evidence_signals={
                                "travel_direction_deg": round(travel_dir, 1),
                                "expected_direction_deg": self._expected_direction,
                                "deviation_deg": round(deviation, 1),
                                "duration_seconds": round(duration, 2),
                                "trajectory_length": len(traj),
                                "vehicle_track_id": vehicle.track_id,
                            },
                            frame_indices=[frame_detections.frame_index],
                            camera_id=frame_detections.camera_id,
                            timestamp=frame_detections.timestamp,
                            trajectory=trajectory_points,
                        )
                    )
                    # Reset trajectory after emission
                    self._trajectories[vehicle.track_id] = []

        # Evict stale tracks
        stale = [tid for tid in self._trajectories if tid not in seen_ids]
        for tid in stale:
            del self._trajectories[tid]

        return candidates

    # ── Helpers ──────────────────────────────────────────────────────

    def _compute_direction(
        self, trajectory: list[tuple[float, float, float]]
    ) -> float | None:
        """
        Compute overall direction of travel from trajectory points.

        Uses displacement between first and last points. Returns degrees
        (0 = right, 90 = down, 180 = left, 270 = up) or None if the
        vehicle is nearly stationary.
        """
        t0, x0, y0 = trajectory[0]
        t1, x1, y1 = trajectory[-1]

        dx = x1 - x0
        dy = y1 - y0
        distance = math.sqrt(dx * dx + dy * dy)

        if distance < 10.0:  # Less than 10 pixels moved — too little to determine
            return None

        angle = math.degrees(math.atan2(dy, dx)) % 360
        return angle

    @staticmethod
    def _angle_difference(a: float, b: float) -> float:
        """Compute the absolute angular difference (0-180 degrees)."""
        diff = abs(a - b) % 360
        return diff if diff <= 180 else 360 - diff

    def _compute_confidence(
        self,
        vehicle: DetectionResult,
        deviation: float,
        duration: float,
    ) -> float:
        """Larger deviation and longer duration → higher confidence."""
        dev_factor = min(deviation / 180.0, 1.0)
        dur_factor = min(duration / (self._min_duration * 3), 1.0)
        return min(1.0, vehicle.confidence * 0.6 + dev_factor * 0.25 + dur_factor * 0.15)
