"""
Illegal parking violation detector.

Identifies vehicles that remain stationary in designated no-parking
zones beyond the allowed time threshold, with congestion filtering
to avoid false positives during traffic jams.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from atved.db.models import ViolationType
from atved.detection import DetectionResult, FrameDetections
from atved.violations.base import BaseViolationDetector, ViolationCandidate
from atved.violations._geometry import bbox_center, point_in_polygon

logger = structlog.get_logger(__name__)


class IllegalParkingDetector(BaseViolationDetector):
    """
    Flags vehicles parked in no-parking zones beyond the time threshold.

    Detection logic:
        1. Define no-parking zones as polygons per camera (from config_json).
        2. Track stationary vehicles — centroid displacement < threshold.
        3. If a vehicle stays stationary in a no-parking zone for longer
           than ``violation_threshold_seconds``, emit a violation.
        4. Congestion filter: if >60% of tracked vehicles in the zone
           are stationary, suppress violations (likely traffic jam, not parking).
    """

    VEHICLE_CLASSES = {"car", "motorcycle", "bus", "truck", "van", "auto_rickshaw"}
    STATIONARY_THRESHOLD_PX = 15.0  # Max centroid displacement to be "stationary"

    def __init__(self, config, violation_type=ViolationType.ILLEGAL_PARKING):
        super().__init__(config, violation_type)
        self._time_threshold = config.violation_threshold_seconds or 300
        self._congestion_filter = config.congestion_filter if config.congestion_filter is not None else True
        self._zones: list[list[tuple[float, float]]] = []
        # track_id → {"first_seen": float, "last_centroid": (x,y), "is_stationary": bool, "zone_id": int}
        self._parked: dict[int, dict[str, Any]] = {}

    def set_zones(self, zones: list[list[tuple[float, float]]]) -> None:
        """Set no-parking zone polygons. Each zone is a list of (x, y) vertices."""
        self._zones = zones

    def analyze(
        self,
        frame_detections: FrameDetections,
        history: list[FrameDetections],
    ) -> list[ViolationCandidate]:
        if not self.is_enabled or not self._zones:
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

            # Check if vehicle is in any no-parking zone
            zone_id = self._find_zone(cx, cy)
            if zone_id is None:
                self._parked.pop(vehicle.track_id, None)
                continue

            state = self._parked.get(vehicle.track_id)
            if state is None:
                self._parked[vehicle.track_id] = {
                    "first_seen": now,
                    "last_centroid": (cx, cy),
                    "is_stationary": True,
                    "zone_id": zone_id,
                    "emitted": False,
                }
                continue

            # Check if still stationary
            lx, ly = state["last_centroid"]
            displacement = ((cx - lx) ** 2 + (cy - ly) ** 2) ** 0.5
            state["last_centroid"] = (cx, cy)

            if displacement > self.STATIONARY_THRESHOLD_PX:
                # Vehicle moved — reset
                state["first_seen"] = now
                state["is_stationary"] = True
                state["emitted"] = False
                continue

            duration = now - state["first_seen"]

            if duration >= self._time_threshold and not state["emitted"]:
                # Check congestion filter
                if self._congestion_filter and self._is_congested(zone_id):
                    logger.debug(
                        "illegal_parking.congestion_suppressed",
                        track_id=vehicle.track_id,
                        zone_id=zone_id,
                    )
                    continue

                confidence = vehicle.confidence * min(duration / (self._time_threshold * 2), 1.0)
                if confidence >= self._config.min_confidence:
                    candidates.append(
                        ViolationCandidate(
                            violation_type=ViolationType.ILLEGAL_PARKING,
                            raw_confidence=confidence,
                            calibrated_confidence=0.0,
                            detections=[vehicle],
                            evidence_signals={
                                "parked_duration_seconds": round(duration, 1),
                                "zone_id": zone_id,
                                "is_congestion_filtered": False,
                                "threshold_seconds": self._time_threshold,
                                "vehicle_track_id": vehicle.track_id,
                            },
                            frame_indices=[frame_detections.frame_index],
                            camera_id=frame_detections.camera_id,
                            timestamp=frame_detections.timestamp,
                        )
                    )
                    state["emitted"] = True

        # Evict stale
        stale = [tid for tid in self._parked if tid not in seen_ids]
        for tid in stale:
            del self._parked[tid]

        return candidates

    def _find_zone(self, x: float, y: float) -> int | None:
        """Return the index of the no-parking zone containing point, or None."""
        for i, zone in enumerate(self._zones):
            if point_in_polygon(x, y, zone):
                return i
        return None

    def _is_congested(self, zone_id: int) -> bool:
        """Check if >60% of vehicles in this zone are stationary (traffic jam)."""
        in_zone = [s for s in self._parked.values() if s["zone_id"] == zone_id]
        if len(in_zone) < 3:
            return False
        stationary = sum(1 for s in in_zone if s["is_stationary"])
        return (stationary / len(in_zone)) > 0.6
