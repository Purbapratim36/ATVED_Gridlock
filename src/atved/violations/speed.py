"""
Speed / over-speed violation detector.

Estimates vehicle speed by measuring pixel displacement of tracked
centroids across frames, converting to real-world speed via a
configurable ``pixels_per_meter`` calibration factor, and flagging
vehicles that exceed the posted ``speed_limit_kmh``.
"""

from __future__ import annotations

import math
from typing import Any

import structlog

from atved.db.models import ViolationType
from atved.detection import DetectionResult, FrameDetections
from atved.violations.base import BaseViolationDetector, ViolationCandidate
from atved.violations._geometry import bbox_center

logger = structlog.get_logger(__name__)


class SpeedViolationDetector(BaseViolationDetector):
    """
    Flags vehicles exceeding the configured speed limit.

    Detection logic:
        1. Track vehicle centroid positions across consecutive frames.
        2. Compute pixel displacement per time interval.
        3. Convert to real-world speed using ``pixels_per_meter``.
        4. If the estimated speed exceeds ``speed_limit_kmh`` for
           longer than ``min_duration_seconds``, emit a violation.

    Calibration is set per-camera via :meth:`set_calibration` with
    ``pixels_per_meter`` (how many pixels equal one metre in the
    camera's view) and ``speed_limit_kmh``.

    Notes
    -----
    Single-camera speed estimation is inherently approximate because
    perspective distortion means ``pixels_per_meter`` varies across
    the frame. For best results, calibrate using known lane markings
    (Indian standard lane = 3.5 m width, dashed lane markers are
    typically 3 m long with 4.5 m gaps).
    """

    VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck", "van", "auto_rickshaw"}
    MIN_TRAJECTORY_POINTS = 4

    def __init__(self, config, violation_type=ViolationType.SPEEDING):
        super().__init__(config, violation_type)
        self._min_duration = config.min_duration_seconds or 1.0

        # Per-camera calibration (set via set_calibration)
        self._pixels_per_meter: float | None = None
        self._speed_limit_kmh: float = 40.0  # Default city speed limit

        # track_id → list of (timestamp_seconds, cx, cy)
        self._trajectories: dict[int, list[tuple[float, float, float]]] = {}

        # track_id → number of consecutive over-speed frames
        self._over_speed_streak: dict[int, int] = {}

    # ── Configuration ────────────────────────────────────────────────

    def set_calibration(
        self,
        pixels_per_meter: float,
        speed_limit_kmh: float | None = None,
    ) -> None:
        """Set per-camera pixel-to-real-world calibration.

        Parameters
        ----------
        pixels_per_meter:
            How many pixels in the camera frame correspond to 1 metre
            on the road surface (at the calibration region).
        speed_limit_kmh:
            Speed limit in km/h for the road monitored by this camera.
            Defaults to 40 km/h if not provided.
        """
        self._pixels_per_meter = pixels_per_meter
        if speed_limit_kmh is not None:
            self._speed_limit_kmh = speed_limit_kmh
        logger.info(
            "speed_detector.calibrated",
            pixels_per_meter=pixels_per_meter,
            speed_limit_kmh=self._speed_limit_kmh,
        )

    # ── Core Analysis ────────────────────────────────────────────────

    def analyze(
        self,
        frame_detections: FrameDetections,
        history: list[FrameDetections],
    ) -> list[ViolationCandidate]:
        if not self.is_enabled or self._pixels_per_meter is None:
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

            # Keep trajectory bounded (last 90 data points ≈ 18 s at 5 fps)
            if len(traj) > 90:
                traj[:] = traj[-90:]

            if len(traj) < self.MIN_TRAJECTORY_POINTS:
                continue

            # Compute instantaneous speed from last few points
            speed_kmh = self._estimate_speed(traj)
            if speed_kmh is None:
                continue

            if speed_kmh > self._speed_limit_kmh:
                streak = self._over_speed_streak.get(vehicle.track_id, 0) + 1
                self._over_speed_streak[vehicle.track_id] = streak

                # Check sustained duration
                duration = traj[-1][0] - traj[0][0]
                if (
                    streak >= self._config.min_consecutive_frames
                    and duration >= self._min_duration
                ):
                    confidence = self._compute_confidence(
                        vehicle, speed_kmh, duration
                    )
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
                                    "over_by_kmh": round(
                                        speed_kmh - self._speed_limit_kmh, 1
                                    ),
                                    "duration_seconds": round(duration, 2),
                                    "trajectory_length": len(traj),
                                    "vehicle_track_id": vehicle.track_id,
                                    "pixels_per_meter": self._pixels_per_meter,
                                },
                                frame_indices=[frame_detections.frame_index],
                                camera_id=frame_detections.camera_id,
                                timestamp=frame_detections.timestamp,
                                trajectory=trajectory_points,
                            )
                        )
                        # Reset after emission to avoid duplicate alerts
                        self._trajectories[vehicle.track_id] = []
                        self._over_speed_streak[vehicle.track_id] = 0
            else:
                # Speed is within limit — decay the streak
                self._over_speed_streak[vehicle.track_id] = 0

        # Evict stale tracks
        stale = [tid for tid in self._trajectories if tid not in seen_ids]
        for tid in stale:
            del self._trajectories[tid]
            self._over_speed_streak.pop(tid, None)

        return candidates

    # ── Helpers ───────────────────────────────────────────────────────

    def _estimate_speed(
        self, trajectory: list[tuple[float, float, float]]
    ) -> float | None:
        """
        Estimate current speed from the last several trajectory points.

        Uses a sliding window of the last 5 points to smooth out
        jitter. Returns speed in km/h, or None if the time delta
        is too small to be meaningful.
        """
        # Use last 5 points for a smoothed estimate
        window = trajectory[-5:]
        t0, x0, y0 = window[0]
        t1, x1, y1 = window[-1]

        dt = t1 - t0
        if dt < 0.1:  # Less than 100 ms — not enough time elapsed
            return None

        dx = x1 - x0
        dy = y1 - y0
        pixel_distance = math.sqrt(dx * dx + dy * dy)

        # Convert pixels → metres → km/h
        metres = pixel_distance / self._pixels_per_meter
        metres_per_second = metres / dt
        kmh = metres_per_second * 3.6

        return kmh

    def _compute_confidence(
        self,
        vehicle: DetectionResult,
        speed_kmh: float,
        duration: float,
    ) -> float:
        """Higher duration → higher confidence."""
        dur_factor = min(duration / (self._min_duration * 3), 1.0)
        return min(
            1.0, vehicle.confidence * 0.8 + dur_factor * 0.2
        )
