"""
Seatbelt violation detector.

Identifies drivers in cars/vans/trucks who are not wearing seatbelts
by analyzing the driver region within the vehicle bounding box.
"""

from __future__ import annotations

from typing import Any

import structlog

from atved.db.models import ViolationType
from atved.detection import DetectionResult, FrameDetections
from atved.violations.base import BaseViolationDetector, ViolationCandidate
from atved.violations._geometry import compute_iou, is_inside

logger = structlog.get_logger(__name__)


class SeatbeltViolationDetector(BaseViolationDetector):
    """
    Flags vehicle drivers who are not wearing a seatbelt.

    Detection logic:
        1. Find all vehicles (car, van, truck, bus).
        2. For each vehicle, find spatially associated drivers.
        3. Evaluate seatbelt visibility — the driver region must be
           clear enough to make a determination (visibility_score).
        4. If driver is visible but no seatbelt is detected, flag it.
        5. Unlike helmet detection, seatbelt is harder to see at distance,
           so we require a higher visibility_score threshold.
    """

    VEHICLE_CLASSES = {"car", "van", "truck", "bus"}
    DRIVER_CLASS = "driver"
    SEATBELT_CLASS = "seatbelt"

    def __init__(self, config, violation_type=ViolationType.SEATBELT):
        super().__init__(config, violation_type)
        self._min_visibility = config.min_visibility_score or 0.6

    def analyze(
        self,
        frame_detections: FrameDetections,
        history: list[FrameDetections],
    ) -> list[ViolationCandidate]:
        if not self.is_enabled:
            return []

        candidates: list[ViolationCandidate] = []
        dets = frame_detections.detections

        vehicles = [d for d in dets if d.class_name in self.VEHICLE_CLASSES]
        drivers = [d for d in dets if d.class_name == self.DRIVER_CLASS]
        seatbelts = [d for d in dets if d.class_name == self.SEATBELT_CLASS]

        for vehicle in vehicles:
            associated_drivers = [
                d for d in drivers
                if is_inside(d.bbox, vehicle.bbox, threshold=0.5)
            ]

            for driver in associated_drivers:
                visibility = self._estimate_visibility(driver, vehicle)
                if visibility < self._min_visibility:
                    continue  # Can't see driver clearly enough

                has_seatbelt = any(
                    compute_iou(driver.bbox, sb.bbox) >= 0.1
                    for sb in seatbelts
                )

                if not has_seatbelt:
                    confidence = min(driver.confidence, vehicle.confidence) * visibility
                    if confidence >= self._config.min_confidence:
                        candidates.append(
                            ViolationCandidate(
                                violation_type=ViolationType.SEATBELT,
                                raw_confidence=confidence,
                                calibrated_confidence=0.0,
                                detections=[vehicle, driver],
                                evidence_signals={
                                    "vehicle_type": vehicle.class_name,
                                    "seatbelt_visible": False,
                                    "visibility_score": round(visibility, 3),
                                    "driver_track_id": driver.track_id,
                                    "vehicle_track_id": vehicle.track_id,
                                },
                                frame_indices=[frame_detections.frame_index],
                                camera_id=frame_detections.camera_id,
                                timestamp=frame_detections.timestamp,
                            )
                        )

        return candidates

    def _estimate_visibility(
        self, driver: DetectionResult, vehicle: DetectionResult
    ) -> float:
        """
        Estimate how clearly the driver is visible.

        Uses the driver bounding box area relative to the vehicle bbox
        and the driver detection confidence as a proxy. A large, high-
        confidence driver detection means the camera has a clear view.
        """
        dx = driver.bbox[2] - driver.bbox[0]
        dy = driver.bbox[3] - driver.bbox[1]
        driver_area = dx * dy

        vx = vehicle.bbox[2] - vehicle.bbox[0]
        vy = vehicle.bbox[3] - vehicle.bbox[1]
        vehicle_area = max(vx * vy, 1.0)

        area_ratio = min(driver_area / vehicle_area, 1.0)
        return area_ratio * driver.confidence
