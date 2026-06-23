"""
Speed / over-speed violation detector.

Estimates vehicle speed by tracking centroids across frames,
and using a Homography matrix to project pixel coordinates to
real-world meters.
"""

from __future__ import annotations

import math
import os
import json
from typing import Any

import cv2
import numpy as np
import structlog

from atved.db.models import ViolationType
from atved.detection import DetectionResult, FrameDetections
from atved.violations.base import BaseViolationDetector, ViolationCandidate
from atved.violations._geometry import bbox_center

logger = structlog.get_logger(__name__)


class CalibrationError(Exception):
    pass


class SpeedViolationDetector(BaseViolationDetector):
    VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck", "van", "auto_rickshaw"}
    MIN_TRAJECTORY_POINTS = 4
    
    FPS = 15
    CONFIRMATION_THRESHOLD = 10
    MIN_DURATION_SECONDS = CONFIRMATION_THRESHOLD / FPS  # ~0.67s minimum

    def __init__(self, config, violation_type=ViolationType.SPEEDING):
        super().__init__(config, violation_type)
        # Use derived constant, overriding config if not specified or arbitrary
        self._min_duration = getattr(config, 'min_duration_seconds', None) or self.MIN_DURATION_SECONDS

        self._homography_matrix: np.ndarray | None = None
        self._speed_limit_kmh: float = 40.0
        self._current_camera_id: str | None = None

        self._trajectories: dict[int, list[tuple[float, float, float]]] = {}
        self._over_speed_streak: dict[int, int] = {}

    def load_calibration(self, camera_id: str) -> None:
        if self._current_camera_id == camera_id and self._homography_matrix is not None:
            return

        calib_file = f"camera_{camera_id}_calib.json"
        if not os.path.exists(calib_file):
            self._homography_matrix = None
            raise CalibrationError(f"Missing homography calibration file: {calib_file}")

        try:
            with open(calib_file, 'r') as f:
                data = json.load(f)
                self._homography_matrix = np.array(data['homography_matrix'], dtype=np.float32)
                if 'speed_limit_kmh' in data:
                    self._speed_limit_kmh = float(data['speed_limit_kmh'])
            self._current_camera_id = camera_id
            logger.info("speed_detector.calibrated", camera_id=camera_id)
        except Exception as e:
            self._homography_matrix = None
            raise CalibrationError(f"Error loading calibration for {camera_id}: {e}")

    def pixel_to_world(self, x: float, y: float, H: np.ndarray) -> tuple[float, float]:
        pt = np.array([[[x, y]]], dtype=np.float32)
        world_pt = cv2.perspectiveTransform(pt, H)
        return float(world_pt[0][0][0]), float(world_pt[0][0][1])

    def analyze(
        self,
        frame_detections: FrameDetections,
        history: list[FrameDetections],
    ) -> list[ViolationCandidate]:
        if not self.is_enabled:
            return []

        camera_id = str(frame_detections.camera_id)
        self.load_calibration(camera_id)

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

            if len(traj) > 90:
                traj[:] = traj[-90:]

            if len(traj) < self.MIN_TRAJECTORY_POINTS:
                continue

            speed_kmh = self._estimate_speed(traj)
            if speed_kmh is None:
                continue

            if speed_kmh > self._speed_limit_kmh:
                streak = self._over_speed_streak.get(vehicle.track_id, 0) + 1
                self._over_speed_streak[vehicle.track_id] = streak

                duration = traj[-1][0] - traj[0][0]
                if (
                    streak >= self.CONFIRMATION_THRESHOLD
                    and duration >= self._min_duration
                ):
                    confidence = self._compute_confidence(vehicle, speed_kmh, duration)
                    if confidence >= self._config.min_confidence:
                        trajectory_points = [(t[1], t[2]) for t in traj]
                        candidates.append(
                            ViolationCandidate(
                                violation_type=ViolationType.SPEEDING,
                                raw_confidence=confidence,
                                calibrated_confidence=0.0,
                                detections=[vehicle],
                                evidence_signals={
                                    "estimated_speed_kmh": round(speed_kmh, 1),
                                    "speed_limit_kmh": self._speed_limit_kmh,
                                    "over_by_kmh": round(speed_kmh - self._speed_limit_kmh, 1),
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
                        self._trajectories[vehicle.track_id] = []
                        self._over_speed_streak[vehicle.track_id] = 0
            else:
                current_streak = self._over_speed_streak.get(vehicle.track_id, 0)
                self._over_speed_streak[vehicle.track_id] = max(0, current_streak - 2)

        stale = [tid for tid in self._trajectories if tid not in seen_ids]
        for tid in stale:
            del self._trajectories[tid]
            self._over_speed_streak.pop(tid, None)

        return candidates

    def _estimate_speed(self, trajectory: list[tuple[float, float, float]]) -> float | None:
        window = trajectory[-5:]
        t0, x0, y0 = window[0]
        t1, x1, y1 = window[-1]

        dt = t1 - t0
        if dt < 0.1:
            return None

        wx0, wy0 = self.pixel_to_world(x0, y0, self._homography_matrix)
        wx1, wy1 = self.pixel_to_world(x1, y1, self._homography_matrix)

        dx = wx1 - wx0
        dy = wy1 - wy0
        metres = math.sqrt(dx * dx + dy * dy)

        metres_per_second = metres / dt
        kmh = metres_per_second * 3.6
        return kmh

    def _compute_confidence(self, vehicle: DetectionResult, speed_kmh: float, duration: float) -> float:
        dur_factor = min(duration / (self._min_duration * 3), 1.0)
        return min(1.0, vehicle.confidence * 0.8 + dur_factor * 0.2)
